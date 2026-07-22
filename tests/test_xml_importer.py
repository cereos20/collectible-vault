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


# Nested CLZ Collectorz XML export sample
CLZ_NESTED_SCHEMA_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<collectorz>
    <data>
        <comicinfo>
            <comiclist>
                <comic>
                    <mainsection>
                        <series>
                            <displayname>Black Knight: Curse of the Ebony Blade</displayname>
                        </series>
                        <title>Black Knight: Curse of the Ebony Blade</title>
                    </mainsection>
                    <issuenr>1</issuenr>
                    <issueext>A</issueext>
                    <publisher>
                        <displayname>Marvel Comics</displayname>
                    </publisher>
                    <coverprice>3.99</coverprice>
                    <currentprice>15.00</currentprice>
                    <grade>
                        <displayname>8.0 Very Fine</displayname>
                        <rating>8.0</rating>
                    </grade>
                    <barcode>75960620023800111</barcode>
                    <coverfrontdefault>https://clz.com/covers/bk1.jpg</coverfrontdefault>
                </comic>
            </comiclist>
        </comicinfo>
    </data>
</collectorz>
"""

# Flat CLZ XML sample
CLZ_FLAT_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<export>
    <comic>
        <Series>The Amazing Spider-Man</Series>
        <Issue>300</Issue>
        <Publisher>Marvel Comics</Publisher>
        <PurchasePrice>$150.00</PurchasePrice>
        <CurrentValue>$1200.00</CurrentValue>
        <Condition>CGC 9.8</Condition>
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


def test_parse_clz_nested_schema():
    items, errors = parse_comic_xml(CLZ_NESTED_SCHEMA_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 1
    
    item = items[0]
    assert item["title"] == "Black Knight: Curse of the Ebony Blade #1A"
    assert item["publisher"] == "Marvel Comics"
    assert item["purchase_price"] == 3.99
    assert item["current_market_value"] == 15.00
    assert item["condition_grade"] == "8.0 Very Fine"
    assert item["barcode"] == "75960620023800111"
    assert item["image_url"] == "https://clz.com/covers/bk1.jpg"
    assert item["metadata_json"]["publisher"] == "Marvel Comics"
    assert item["metadata_json"]["barcode"] == "75960620023800111"
    assert item["metadata_json"]["cover_url"] == "https://clz.com/covers/bk1.jpg"


def test_parse_clz_flat_xml():
    items, errors = parse_comic_xml(CLZ_FLAT_XML_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 1
    
    item = items[0]
    assert item["title"] == "The Amazing Spider-Man #300"
    assert item["publisher"] == "Marvel Comics"
    assert item["purchase_price"] == 150.00
    assert item["current_market_value"] == 1200.00
    assert item["condition_grade"] == "CGC 9.8"


def test_parse_comicbase_xml():
    items, errors = parse_comic_xml(COMICBASE_XML_SAMPLE)
    assert len(errors) == 0
    assert len(items) == 1
    
    item = items[0]
    assert item["title"] == "Batman #423"
    assert item["publisher"] == "DC Comics"
    assert item["purchase_price"] == 25.00
    assert item["current_market_value"] == 350.00


def test_import_comics_from_xml_db_insertion():
    db = SessionLocal()
    try:
        result = import_comics_from_xml(db, CLZ_NESTED_SCHEMA_SAMPLE)
        assert result["status"] == "success"
        assert result["imported_count"] == 1
        assert len(result["errors"]) == 0

        # Verify DB entry
        item = db.query(CollectibleItem).filter(CollectibleItem.title.like("%Black Knight%")).first()
        assert item is not None
        assert item.category == "comic"
        assert item.barcode == "75960620023800111"
        assert item.image_url == "https://clz.com/covers/bk1.jpg"
        assert item.metadata_json["publisher"] == "Marvel Comics"

        # Verify valuation history entry
        vh = db.query(ValuationHistory).filter(ValuationHistory.item_id == item.id).first()
        assert vh is not None
        assert vh.value == 15.00
    finally:
        db.close()


def test_xml_import_api_endpoint():
    response = client.post(
        "/api/import/xml",
        files={"file": ("clz_collectorz.xml", CLZ_NESTED_SCHEMA_SAMPLE.encode("utf-8"), "application/xml")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["imported_count"] == 1
    assert len(data["errors"]) == 0
