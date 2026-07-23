import json
import math

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import QuizOut, QuizResult, QuizSubmission
from ..services.gemini import STAGES

router = APIRouter(prefix="/api/learning", tags=["learning"])

# Stacks with dedicated addendum content, e.g. stages/{stage}.python.md.
STACKS = ("python", "typescript")


@router.get("/stages")
def list_stages():
    return {"stages": STAGES}


@router.get("/{stage}")
def get_stage_content(stage: str, stack: str | None = None):
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail="Unknown stage")
    path = settings.content_dir / "stages" / f"{stage}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No content for this stage yet")

    markdown = path.read_text(encoding="utf-8")
    available_stacks = [
        s for s in STACKS if (settings.content_dir / "stages" / f"{stage}.{s}.md").is_file()
    ]
    if stack in available_stacks:
        addendum_path = settings.content_dir / "stages" / f"{stage}.{stack}.md"
        markdown = markdown + "\n\n---\n\n" + addendum_path.read_text(encoding="utf-8")

    return {"stage": stage, "markdown": markdown, "stacks": available_stacks}


def _load_quiz_questions(stage: str) -> list[dict]:
    path = settings.content_dir / "quizzes" / f"{stage}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No quiz for this stage yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["questions"]


@router.get("/{stage}/quiz", response_model=QuizOut)
def get_quiz(stage: str):
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail="Unknown stage")
    questions = _load_quiz_questions(stage)
    return QuizOut(
        stage=stage,
        questions=[{"q": q["q"], "options": q["options"]} for q in questions],
    )


@router.post("/{stage}/quiz", response_model=QuizResult)
def submit_quiz(stage: str, payload: QuizSubmission):
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail="Unknown stage")
    questions = _load_quiz_questions(stage)
    if len(payload.answers) != len(questions):
        raise HTTPException(
            status_code=422,
            detail=f"Expected {len(questions)} answers, got {len(payload.answers)}",
        )

    score = 0
    review = []
    for question, given in zip(questions, payload.answers):
        if given == question["answer"]:
            score += 1
        else:
            review.append(
                {
                    "q": question["q"],
                    "correct": question["answer"],
                    "your": given,
                    "why": question["why"],
                }
            )

    total = len(questions)
    passed = score >= math.ceil(total * 2 / 3)
    return QuizResult(score=score, total=total, passed=passed, review=review)
