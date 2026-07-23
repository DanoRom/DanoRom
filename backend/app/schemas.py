from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    template: str = "blank"  # blank | nextjs-app | fastapi-api | fullstack


class PathwayStep(BaseModel):
    title: str
    detail: str = ""


class PathwayBranch(BaseModel):
    title: str
    description: str = ""
    priority: str = "recommended"  # recommended | optional | critical
    steps: list[PathwayStep] = []


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    confidence: int
    summary: str
    engine: str
    created_at: datetime
    branches: list[PathwayBranch] = []
    chosen_branch: int = -1
    completed_steps: list[int] = []


class ChooseBranch(BaseModel):
    branch_index: int


class StepUpdate(BaseModel):
    step_index: int
    done: bool


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    source_type: str
    template: str
    stage: str
    created_at: datetime


class ProjectDetail(ProjectOut):
    latest_evaluation: EvaluationOut | None = None


class QuizQuestion(BaseModel):
    q: str
    options: list[str]


class QuizOut(BaseModel):
    stage: str
    questions: list[QuizQuestion]


class QuizSubmission(BaseModel):
    answers: list[int]


class QuizReviewItem(BaseModel):
    q: str
    correct: int
    your: int
    why: str


class QuizResult(BaseModel):
    score: int
    total: int
    passed: bool
    review: list[QuizReviewItem]
