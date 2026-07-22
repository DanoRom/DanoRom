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
