import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import ensure_project_access, get_current_user_optional
from ..database import get_db
from ..models import Project, User
from ..services import gemini, scanner

router = APIRouter(prefix="/api/projects", tags=["coach"])


class CoachRequest(BaseModel):
    branch_index: int
    step_index: int


class CoachOut(BaseModel):
    markdown: str
    engine: str


@router.post("/{project_id}/coach", response_model=CoachOut)
def coach_step(
    project_id: int,
    payload: CoachRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    if not project.evaluations:
        raise HTTPException(status_code=409, detail="Evaluate the project first")
    if not project.root_path or not Path(project.root_path).is_dir():
        raise HTTPException(status_code=409, detail="Project has no files to scan")

    evaluation = project.evaluations[0]
    branches = json.loads(evaluation.branches_json or "[]")
    if not 0 <= payload.branch_index < len(branches):
        raise HTTPException(status_code=422, detail="Invalid branch index")
    branch = branches[payload.branch_index]
    steps = branch.get("steps", [])
    if not 0 <= payload.step_index < len(steps):
        raise HTTPException(status_code=422, detail="Invalid step index")

    scan = scanner.scan_project(project.root_path)
    result = gemini.coach_step(scan, evaluation.stage, branch, steps[payload.step_index])
    return CoachOut(**result)
