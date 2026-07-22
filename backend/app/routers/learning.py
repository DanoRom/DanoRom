from fastapi import APIRouter, HTTPException

from ..config import settings
from ..services.gemini import STAGES

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/stages")
def list_stages():
    return {"stages": STAGES}


@router.get("/{stage}")
def get_stage_content(stage: str):
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail="Unknown stage")
    path = settings.content_dir / "stages" / f"{stage}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No content for this stage yet")
    return {"stage": stage, "markdown": path.read_text(encoding="utf-8")}
