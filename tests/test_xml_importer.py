import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, init_db, SessionLocal
from app.models import CollectibleItem, ValuationHistory
from app.importers.xml_importer import parse_comic_xml, import_comics_from_xml

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Sample XML data
CLZ_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<export>
    <comic>
        <Series>The Amazing Spider-Man</Series>
        <Issue>300</Issue>
        <Publisher>Marvel Comics</Publisher>
        <PurchasePrice>$150.00</PurchasePrice>
        <CurrentValue>$1200.00</CurrentValue>
        <Condition>CGC 9.8</Condition>
    </comic>
    <comic>
        <Series>Uncanny X-Men</Series>
        <Issue>266</Issue>
        <Publisher>Marvel Comics</Publisher>
        <PurchasePrice>$45.00</PurchasePrice>
        <CurrentValue>$250.00</CurrentValue>
        <Condition>VF/NM</Condition>
    </comic>
</export>
"""

COMICBASE_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<collection>
    <item>
        <BookTitle>Batman</BookTitle>
        <IssueNum>423</IssueNum>
        <Publisher>DC Comics</Publisher>
        <Cost>25.00</Cost>
        <EstValue>350.00</EstValue>
        <Grade>Near Mint</Grade>
    </item>
</collection>
"""

LOCG_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<comics>
    <row>
        <title>Saga #1</title>
        <issue>1</issue>
        <publisher>Image Comics</publisher>
        <price>2.99</price>
        <value>180.00</value>
        <format>NM 9.4</format>
    </row>
</comics>
"""


def test_parse_clz_xml():
    items, errors = parse_comic_xml(CLZ_XML_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 2
    
    item1 = items[0]
    assert item1["title"] == "The Amazing Spider-Man #300"
    assert item1["publisher"] == "Marvel Comics"
    assert item1["purchase_price"] == 150.00
    assert item1["current_market_value"] == 1200.00
    assert item1["condition_grade"] == "CGC 9.8"
    assert item1["category"] == "comic"


def test_parse_comicbase_xml():
    items, errors = parse_comic_xml(COMICBASE_XML_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 1
    
    item = items[0]
    assert item["title"] == "Batman #423"
    assert item["publisher"] == "DC Comics"
    assert item["purchase_price"] == 25.00
    assert item["current_market_value"] == 350.00
    assert item["condition_grade"] == "Near Mint"


def test_parse_locg_xml():
    items, errors = parse_comic_xml(LOCG_XML_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 1
    
    item = items[0]
    assert item["title"] == "Saga #1"
    assert item["publisher"] == "Image Comics"
    assert item["purchase_price"] == 2.99
    assert item["current_market_value"] == 180.00
    assert item["condition_grade"] == "NM 9.4"


def test_import_comics_from_xml_db_insertion():
    db = SessionLocal()
    try:
        result = import_comics_from_xml(db, CLZ_XML_SAMPLE)
        assert result["status"] == "success"
        assert result["imported_count"] == 2
        assert len(result["errors"]) == 0

        # Verify DB entries
        db_items = db.query(CollectibleItem).filter(CollectibleItem.category == "comic").all()
        assert len(db_items) >= 2

        titles = [i.title for i in db_items]
        assert "The Amazing Spider-Man #300" in titles
        assert "Uncanny X-Men #266" in titles

        # Verify valuation history entries
        vh_entries = db.query(ValuationHistory).all()
        assert len(vh_entries) >= 2
        vh_values = [v.value for v in vh_entries]
        assert 1200.00 in vh_values
        assert 250.00 in vh_values
    finally:
        db.close()


def test_xml_import_api_endpoint():
    response = client.post(
        "/api/import/xml",
        files={"file": ("clz_export.xml", CLZ_XML_SAMPLE.encode("utf-8"), "application/xml")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["imported_count"] == 2
    assert len(data["errors"]) == 0

    # Test empty file error handling
    empty_resp = client.post(
        "/api/import/xml",
        files={"file": ("empty.xml", b"", "application/xml")}
    )
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["status"] == "error"
    assert empty_data["imported_count"] == 0
    assert "Uploaded XML file is empty." in empty_data["errors"]
