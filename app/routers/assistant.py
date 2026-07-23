from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.llm_assistant import query_vault_assistant

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


class AssistantChatRequest(BaseModel):
    prompt: str
    model: Optional[str] = None


@router.post("/chat")
async def assistant_chat(payload: AssistantChatRequest, db: Session = Depends(get_db)):
    """
    FastMCP / Ollama vault assistant endpoint.
    Accepts user prompt and optional model parameter, queries LLM service with portfolio context.
    """
    if not payload.prompt or not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt parameter cannot be empty.")

    result = await query_vault_assistant(
        user_prompt=payload.prompt.strip(),
        selected_model=payload.model,
        db=db
    )
    return result
