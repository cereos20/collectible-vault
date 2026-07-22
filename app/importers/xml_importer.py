import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Tuple, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import CollectibleItem, ValuationHistory


def parse_currency(val_str: str) -> float:
    """Parses numeric float from currency/price string."""
    if not val_str:
        return 0.0
    try:
        # Strip currency symbols, commas, spaces
        cleaned = re.sub(r"[^\d.-]", "", val_str)
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def extract_tag_value(element: ET.Element, tag_candidates: List[str]) -> str:
    """
    Searches child tags and element attributes for matching tag candidates (case-insensitive).
    """
    # Normalize candidates
    cand_set = {c.lower().replace("_", "").replace("-", "") for c in tag_candidates}

    # Check child tags first
    for child in element:
        normalized_tag = child.tag.lower().replace("_", "").replace("-", "")
        # Remove XML namespace if present
        if "}" in normalized_tag:
            normalized_tag = normalized_tag.split("}", 1)[1]
        
        if normalized_tag in cand_set and child.text:
            val = child.text.strip()
            if val:
                return val

    # Check attributes if not found in child elements
    for attr_key, attr_val in element.attrib.items():
        normalized_attr = attr_key.lower().replace("_", "").replace("-", "")
        if normalized_attr in cand_set and attr_val:
            return attr_val.strip()

    return ""


def find_comic_elements(root: ET.Element) -> List[ET.Element]:
    """
    Traverses XML tree to find elements representing individual comic book records.
    """
    record_elements = []

    def is_leaf_container(elem: ET.Element) -> bool:
        """Returns True if element's children are primitive leaf nodes (no nested complex children)."""
        if len(elem) == 0:
            return False
        for child in elem:
            if len(child) > 0:
                return False
        return True

    # Traverse all elements in tree
    for elem in root.iter():
        if elem == root:
            continue
        
        # Check tag name or structure
        tag_lower = elem.tag.lower()
        if "}" in tag_lower:
            tag_lower = tag_lower.split("}", 1)[1]

        # Explicit comic item tags or leaf containers matching fields
        known_record_tags = {"comic", "item", "book", "row", "comicbook", "entry", "record", "exportitem"}
        
        if tag_lower in known_record_tags or is_leaf_container(elem):
            # Verify if element contains at least one comic-related field
            sample_val = extract_tag_value(elem, [
                "title", "series", "seriesname", "booktitle", "issue", "issuenum", "issuenumber", "publisher"
            ])
            if sample_val:
                record_elements.append(elem)

    return record_elements


def parse_comic_xml(xml_content: bytes | str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses comic book XML exports from CLZ/Collectorz, ComicBase, League of Comic Geeks, etc.
    Returns (list of parsed comic dicts, list of error messages).
    """
    items = []
    errors = []

    if isinstance(xml_content, str):
        xml_bytes = xml_content.encode("utf-8")
    else:
        xml_bytes = xml_content

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return [], [f"Failed to parse XML file format: {str(e)}"]

    comic_nodes = find_comic_elements(root)
    if not comic_nodes:
        return [], ["No valid comic book records found in the XML file."]

    for idx, node in enumerate(comic_nodes, start=1):
        try:
            # 1. Title / Series Name: <title>, <Series>, <SeriesName>, <BookTitle>
            title = extract_tag_value(node, ["title", "series", "seriesname", "booktitle", "name"])
            
            # 2. Issue Number: <issue>, <Issue>, <IssueNum>, <IssueNumber>
            issue = extract_tag_value(node, ["issue", "issuenum", "issuenumber", "number", "no"])

            # 3. Publisher: <publisher>, <Publisher>
            publisher = extract_tag_value(node, ["publisher", "pub", "publishername"])

            # 4. Purchase Price: <price>, <PurchasePrice>, <Cost>
            price_raw = extract_tag_value(node, ["price", "purchaseprice", "cost", "boughtprice", "buyprice"])
            purchase_price = parse_currency(price_raw)

            # 5. Market Value: <value>, <CurrentValue>, <EstValue>
            value_raw = extract_tag_value(node, ["value", "currentvalue", "estvalue", "marketvalue", "estimatedvalue"])
            market_value = parse_currency(value_raw)

            # 6. Condition/Grade: <condition>, <Grade>, <Format>
            condition = extract_tag_value(node, ["condition", "grade", "format", "cgcgrade"]) or "Near Mint"

            # Title normalization
            if not title and publisher:
                title = f"{publisher} Comic"
            elif not title:
                title = "Untitled Comic"

            # Format title with issue number if issue exists and isn't already included in title
            if issue:
                issue_clean = issue.lstrip("#").strip()
                if issue_clean and not (f"#{issue_clean}" in title or title.endswith(f" {issue_clean}")):
                    full_title = f"{title} #{issue_clean}"
                else:
                    full_title = title
            else:
                full_title = title

            metadata_json = {
                "issue_number": issue or None,
                "publisher": publisher or None,
                "imported_via": "XML Bulk Import",
                "raw_condition": condition
            }

            items.append({
                "title": full_title,
                "category": "comic",
                "purchase_price": purchase_price,
                "current_market_value": market_value,
                "condition_grade": condition,
                "publisher": publisher,
                "issue": issue,
                "metadata_json": metadata_json
            })
        except Exception as err:
            errors.append(f"Row {idx}: Error parsing item record - {str(err)}")

    return items, errors


def import_comics_from_xml(db: Session, xml_content: bytes | str) -> Dict[str, Any]:
    """
    Parses XML, batch inserts items into 'collectibles' table with category='comic',
    and writes initial entries into 'valuation_history' for items with market values.
    """
    parsed_items, errors = parse_comic_xml(xml_content)

    if not parsed_items and errors:
        return {
            "status": "error",
            "imported_count": 0,
            "errors": errors
        }

    imported_count = 0
    now = datetime.utcnow()

    for item_data in parsed_items:
        try:
            notes_str = f"Publisher: {item_data['publisher']}" if item_data['publisher'] else "Imported via XML"
            
            collectible = CollectibleItem(
                title=item_data["title"],
                category="comic",
                purchase_price=item_data["purchase_price"],
                current_market_value=item_data["current_market_value"],
                condition_grade=item_data["condition_grade"],
                notes=notes_str,
                metadata_json=item_data["metadata_json"],
                created_at=now,
                updated_at=now
            )
            db.add(collectible)
            db.flush()  # Populates collectible.id

            # Initial valuation history for items with market values
            if item_data["current_market_value"] > 0:
                val_history = ValuationHistory(
                    item_id=collectible.id,
                    value=item_data["current_market_value"],
                    recorded_at=now,
                    source="XML Import Initial Valuation"
                )
                db.add(val_history)

            imported_count += 1
        except Exception as e:
            errors.append(f"Failed to save comic '{item_data.get('title')}': {str(e)}")

    db.commit()

    status = "success" if imported_count > 0 and not errors else ("partial" if imported_count > 0 else "error")

    return {
        "status": status,
        "imported_count": imported_count,
        "errors": errors
    }
