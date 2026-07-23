import os
import time
import re
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import VisionIntakeResponse
from app.vision_ai import analyze_collectible_image
from app.services.key_detector import detect_key_issue
from app.services.image_healer import get_fallback_badge

router = APIRouter(prefix="/api/intake", tags=["Intake"])
logger = logging.getLogger("vault.intake")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/vision", response_model=VisionIntakeResponse)
async def intake_by_vision(file: UploadFile = File(...)):
    """
    Accepts photo upload of collectible cover/box, runs Vision AI (or mock recognition fallback),
    saves photo to /uploads/, detects key issues, and returns structured JSON metadata.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided for vision intake.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Save uploaded image to /uploads/ directory
    safe_filename = re.sub(r'[^a-zA-Z0-9_\.-]', '_', file.filename)
    unique_filename = f"vision_{int(time.time())}_{safe_filename}"
    saved_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(saved_path, "wb") as f:
            f.write(contents)
        image_url = f"/uploads/{unique_filename}"
    except Exception as e:
        logger.warning(f"Could not save vision upload file: {e}")
        image_url = get_fallback_badge("other")

    # Analyze image via Vision LLM
    result = await analyze_collectible_image(contents, filename=file.filename)

    title = result.get("title", "Unknown Collectible")
    category = result.get("category", "other")

    # Detect key issue
    is_key, key_reasons = detect_key_issue(title)

    return VisionIntakeResponse(
        title=title,
        category=category,
        publisher_or_brand=result.get("publisher_or_brand"),
        issue_or_box_number=result.get("issue_or_box_number"),
        condition_estimate=result.get("condition_estimate", "Near Mint"),
        estimated_market_value=float(result.get("estimated_market_value", 0.0)),
        confidence_score=float(result.get("confidence_score", 0.85)),
        extracted_metadata=result.get("extracted_metadata", {}),
        summary=result.get("summary", "Successfully analyzed image via Vision AI."),
        image_url=image_url,
        is_key_issue=is_key,
        key_reasons=key_reasons
    )
