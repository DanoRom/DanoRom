import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Evaluation, Project

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_projects = db.query(Project).count()
    evaluations = db.query(Evaluation).all()
    total_evaluations = len(evaluations)
    steps_completed = sum(
        len(json.loads(evaluation.completed_steps_json or "[]")) for evaluation in evaluations
    )
    gemini_evaluations = sum(1 for evaluation in evaluations if evaluation.engine == "gemini")

    stage_counts: dict[str, int] = {}
    for project in db.query(Project).all():
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
