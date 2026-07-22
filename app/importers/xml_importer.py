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
        cleaned = re.sub(r"[^\d.-]", "", val_str)
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_node_text(node: ET.Element, paths: List[str]) -> str:
    """Searches element node using relative XPath paths or child tags for non-empty text."""
    for path in paths:
        found = node.find(path)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return ""


def extract_tag_value(element: ET.Element, tag_candidates: List[str]) -> str:
    """
    Searches child tags and element attributes for matching tag candidates (case-insensitive).
    """
    cand_set = {c.lower().replace("_", "").replace("-", "") for c in tag_candidates}

    for child in element:
        normalized_tag = child.tag.lower().replace("_", "").replace("-", "")
        if "}" in normalized_tag:
            normalized_tag = normalized_tag.split("}", 1)[1]
        
        if normalized_tag in cand_set and child.text:
            val = child.text.strip()
            if val:
                return val

    for attr_key, attr_val in element.attrib.items():
        normalized_attr = attr_key.lower().replace("_", "").replace("-", "")
        if normalized_attr in cand_set and attr_val:
            return attr_val.strip()

    return ""


def find_comic_elements(root: ET.Element) -> List[ET.Element]:
    """
    Traverses XML tree to find elements representing individual comic book records.
    Supports CLZ nested structure (<collectorz>...<comic>) and generic XML trees.
    """
    # 1. Check for explicit CLZ/Collectorz XPath nodes (.//comic or .//comiclist/comic)
    clz_nodes = root.findall(".//comiclist/comic") or root.findall(".//comic")
    if clz_nodes:
        return clz_nodes

    # 2. Generic fallback scanner
    record_elements = []

    def is_leaf_container(elem: ET.Element) -> bool:
        if len(elem) == 0:
            return False
        for child in elem:
            if len(child) > 0:
                return False
        return True

    for elem in root.iter():
        if elem == root:
            continue
        
        tag_lower = elem.tag.lower()
        if "}" in tag_lower:
            tag_lower = tag_lower.split("}", 1)[1]

        known_record_tags = {"comic", "item", "book", "row", "comicbook", "entry", "record", "exportitem"}
        
        if tag_lower in known_record_tags or is_leaf_container(elem):
            sample_val = extract_tag_value(elem, [
                "title", "series", "seriesname", "booktitle", "issue", "issuenum", "issuenumber", "publisher"
            ])
            if sample_val:
                record_elements.append(elem)

    return record_elements


def parse_single_comic_node(node: ET.Element) -> Dict[str, Any]:
    """
    Parses a single comic XML node supporting both CLZ nested schema and generic flat schema.
    """
    # --- CLZ Specific Field Extraction ---
    # Series Name / Title: <mainsection><series><displayname> or <mainsection><title>
    series_name = get_node_text(node, [
        ".//mainsection/series/displayname",
        "mainsection/series/displayname",
        ".//series/displayname",
        "series/displayname"
    ])
    
    fallback_title = get_node_text(node, [
        ".//mainsection/title",
        "mainsection/title",
        "title"
    ]) or extract_tag_value(node, ["title", "series", "seriesname", "booktitle", "name"])

    # Issue Number: <issuenr> (+ <issueext> if present)
    issue_nr = get_node_text(node, [".//issuenr", "issuenr"]) or extract_tag_value(node, ["issue", "issuenum", "issuenumber", "number", "no"])
    issue_ext = get_node_text(node, [".//issueext", "issueext"])
    
    if issue_nr and issue_ext:
        issue = f"{issue_nr}{issue_ext}"
    else:
        issue = issue_nr

    # Publisher: <publisher><displayname>
    publisher = get_node_text(node, [
        ".//publisher/displayname",
        "publisher/displayname"
    ]) or extract_tag_value(node, ["publisher", "pub", "publishername"])

    # Purchase / Cover Price: <coverprice> or <price>
    price_raw = get_node_text(node, [
        ".//coverprice",
        "coverprice"
    ]) or extract_tag_value(node, ["price", "purchaseprice", "cost", "boughtprice", "buyprice"])
    purchase_price = parse_currency(price_raw)

    # Current Market Value: <currentprice> or <value>
    value_raw = get_node_text(node, [
        ".//currentprice",
        "currentprice"
    ]) or extract_tag_value(node, ["value", "currentvalue", "estvalue", "marketvalue", "estimatedvalue"])
    market_value = parse_currency(value_raw)

    # Condition / Grade: <grade><displayname> or <grade><rating> or <condition>
    grade_str = get_node_text(node, [
        ".//grade/displayname",
        "grade/displayname",
        ".//grade/rating",
        "grade/rating"
    ]) or extract_tag_value(node, ["condition", "grade", "format", "cgcgrade"]) or "Raw"

    # Barcode: <barcode>
    barcode = get_node_text(node, [".//barcode", "barcode"]) or extract_tag_value(node, ["barcode", "upc", "ean"]) or None

    # Cover Image URL: <coverfrontdefault>
    cover_url = get_node_text(node, [".//coverfrontdefault", "coverfrontdefault"]) or extract_tag_value(node, ["coverfrontdefault", "imageurl", "image", "cover"]) or None

    # --- Title Construction ---
    primary_series = series_name or fallback_title
    if primary_series and issue:
        issue_clean = issue.lstrip("#").strip()
        if issue_clean and not (f"#{issue_clean}" in primary_series or primary_series.endswith(f" {issue_clean}")):
            full_title = f"{primary_series} #{issue_clean}"
        else:
            full_title = primary_series
    elif primary_series:
        full_title = primary_series
    elif publisher:
        full_title = f"{publisher} Comic"
    else:
        full_title = "Untitled Comic"

    metadata_json = {
        "publisher": publisher or None,
        "barcode": barcode or None,
        "cover_url": cover_url or None,
        "issue_number": issue or None,
        "imported_via": "XML Bulk Import",
        "raw_condition": grade_str
    }

    return {
        "title": full_title,
        "category": "comic",
        "purchase_price": purchase_price,
        "current_market_value": market_value,
        "condition_grade": grade_str,
        "publisher": publisher,
        "issue": issue,
        "barcode": barcode,
        "image_url": cover_url,
        "metadata_json": metadata_json
    }


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
            parsed_item = parse_single_comic_node(node)
            items.append(parsed_item)
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
                barcode=item_data.get("barcode"),
                image_url=item_data.get("image_url"),
                metadata_json=item_data["metadata_json"],
                created_at=now,
                updated_at=now
            )
            db.add(collectible)
            db.flush()

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
