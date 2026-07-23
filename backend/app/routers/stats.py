import json

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..models import Evaluation, Project, User

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project_query = db.query(Project)
    if user is not None:
        project_query = project_query.filter(
            or_(Project.owner_id == user.id, Project.owner_id.is_(None))
        )
    else:
        project_query = project_query.filter(Project.owner_id.is_(None))
    projects = project_query.all()
    project_ids = [p.id for p in projects]

    total_projects = len(projects)
    evaluations = (
        db.query(Evaluation).filter(Evaluation.project_id.in_(project_ids)).all()
        if project_ids
        else []
    )
    total_evaluations = len(evaluations)
    steps_completed = sum(
        len(json.loads(evaluation.completed_steps_json or "[]")) for evaluation in evaluations
    )
    gemini_evaluations = sum(1 for evaluation in evaluations if evaluation.engine == "gemini")

    stage_counts: dict[str, int] = {}
    for project in projects:
        if project.stage == "unevaluated":
            continue
        stage_counts[project.stage] = stage_counts.get(project.stage, 0) + 1

    return {
        "total_projects": total_projects,
        "total_evaluations": total_evaluations,
        "steps_completed": steps_completed,
        "stage_counts": stage_counts,
        "gemini_evaluations": gemini_evaluations,
    }
