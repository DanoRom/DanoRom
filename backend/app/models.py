from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(20), default="template")  # template | upload | github
    template: Mapped[str] = mapped_column(String(50), default="")
    root_path: Mapped[str] = mapped_column(String(500), default="")
    stage: Mapped[str] = mapped_column(String(50), default="unevaluated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Evaluation.id.desc()"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    summary: Mapped[str] = mapped_column(Text, default="")
    branches_json: Mapped[str] = mapped_column(Text, default="[]")
    engine: Mapped[str] = mapped_column(String(20), default="heuristic")  # gemini | heuristic
    chosen_branch: Mapped[int] = mapped_column(Integer, default=-1)  # -1 = none chosen yet
    completed_steps_json: Mapped[str] = mapped_column(Text, default="[]")
    signals_json: Mapped[str] = mapped_column(Text, default="{}")  # scanner signals snapshot, for diffing
    changes_json: Mapped[str] = mapped_column(Text, default="[]")  # human-readable diff vs previous evaluation
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="evaluations")
