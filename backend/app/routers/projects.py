import json
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Evaluation, Project
from ..schemas import (
    ChooseBranch,
    EvaluationOut,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    StepUpdate,
)
from ..services import gemini, scanner, templates

router = APIRouter(prefix="/api/projects", tags=["projects"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024


def _project_dir(project_id: int) -> Path:
    return settings.storage_dir / f"project-{project_id}"


def _evaluation_out(evaluation: Evaluation | None) -> EvaluationOut | None:
    if evaluation is None:
        return None
    return EvaluationOut(
        id=evaluation.id,
        stage=evaluation.stage,
        confidence=evaluation.confidence,
        summary=evaluation.summary,
        engine=evaluation.engine,
        created_at=evaluation.created_at,
        branches=json.loads(evaluation.branches_json or "[]"),
        chosen_branch=evaluation.chosen_branch,
        completed_steps=json.loads(evaluation.completed_steps_json or "[]"),
    )


def _latest_evaluation(project: Project) -> Evaluation:
    if not project.evaluations:
        raise HTTPException(status_code=409, detail="Evaluate the project first")
    return project.evaluations[0]


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Project name is required")
    project = Project(
        name=payload.name.strip(),
        description=payload.description.strip(),
        source_type="template",
        template=payload.template,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    dest = _project_dir(project.id)
    templates.create_from_template(payload.template, dest, project.name, project.description)
    project.root_path = str(dest)
    db.commit()
    db.refresh(project)
    return project


@router.post("/upload", response_model=ProjectOut, status_code=201)
async def upload_project(
    file: UploadFile,
    name: str = "",
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Upload a .zip archive of the project")

    project = Project(
        name=name.strip() or Path(file.filename).stem,
        source_type="upload",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    dest = _project_dir(project.id)
    dest.mkdir(parents=True, exist_ok=True)
    archive_path = dest.with_suffix(".zip")

    size = 0
    with archive_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                archive_path.unlink(missing_ok=True)
                db.delete(project)
                db.commit()
                raise HTTPException(status_code=413, detail="Archive exceeds 50 MB limit")
            out.write(chunk)

    try:
        _safe_extract(archive_path, dest)
    except (zipfile.BadZipFile, ValueError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        archive_path.unlink(missing_ok=True)
        db.delete(project)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Invalid archive: {exc}")
    finally:
        archive_path.unlink(missing_ok=True)

    project.root_path = str(dest)
    db.commit()
    db.refresh(project)
    return project


def _safe_extract(archive_path: Path, dest: Path) -> None:
    """Extracts a zip while blocking path traversal and zip bombs."""
    with zipfile.ZipFile(archive_path) as archive:
        total = 0
        for info in archive.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("archive contains paths outside the project root")
            total += info.file_size
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError("archive expands beyond the 200 MB limit")
        archive.extractall(dest)


@router.post("/{project_id}/reupload", response_model=ProjectOut)
async def reupload_project(project_id: int, file: UploadFile, db: Session = Depends(get_db)):
    """Replaces a project's files with a new archive so re-evaluation reflects real progress."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Upload a .zip archive of the project")

    incoming = settings.storage_dir / f"project-{project.id}-incoming"
    shutil.rmtree(incoming, ignore_errors=True)
    incoming.mkdir(parents=True)
    archive_path = incoming.with_suffix(".zip")

    try:
        size = 0
        with archive_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Archive exceeds 50 MB limit")
                out.write(chunk)
        _safe_extract(archive_path, incoming)
    except (zipfile.BadZipFile, ValueError) as exc:
        shutil.rmtree(incoming, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"Invalid archive: {exc}")
    except HTTPException:
        shutil.rmtree(incoming, ignore_errors=True)
        raise
    finally:
        archive_path.unlink(missing_ok=True)

    dest = _project_dir(project.id)
    shutil.rmtree(dest, ignore_errors=True)
    incoming.rename(dest)
    project.root_path = str(dest)
    project.source_type = "upload"  # a templated project becomes user-owned files once replaced
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    detail = ProjectDetail.model_validate(project)
    detail.latest_evaluation = _evaluation_out(
        project.evaluations[0] if project.evaluations else None
    )
    return detail


@router.post("/{project_id}/evaluate", response_model=EvaluationOut)
def evaluate_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.root_path or not Path(project.root_path).is_dir():
        raise HTTPException(status_code=409, detail="Project has no files to scan")

    scan = scanner.scan_project(project.root_path)
    result = gemini.evaluate(scan)

    evaluation = Evaluation(
        project_id=project.id,
        stage=result["stage"],
        confidence=result["confidence"],
        summary=result["summary"],
        branches_json=json.dumps(result["branches"]),
        engine=result["engine"],
    )
    project.stage = result["stage"]
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return _evaluation_out(evaluation)


@router.post("/{project_id}/pathway", response_model=EvaluationOut)
def choose_pathway(project_id: int, payload: ChooseBranch, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    evaluation = _latest_evaluation(project)
    branches = json.loads(evaluation.branches_json or "[]")
    if not 0 <= payload.branch_index < len(branches):
        raise HTTPException(status_code=422, detail="Invalid branch index")
    if evaluation.chosen_branch != payload.branch_index:
        evaluation.chosen_branch = payload.branch_index
        evaluation.completed_steps_json = "[]"  # switching paths resets progress
    db.commit()
    db.refresh(evaluation)
    return _evaluation_out(evaluation)


@router.post("/{project_id}/pathway/steps", response_model=EvaluationOut)
def update_step(project_id: int, payload: StepUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    evaluation = _latest_evaluation(project)
    if evaluation.chosen_branch < 0:
        raise HTTPException(status_code=409, detail="Choose a pathway first")
    branches = json.loads(evaluation.branches_json or "[]")
    steps = branches[evaluation.chosen_branch].get("steps", [])
    if not 0 <= payload.step_index < len(steps):
        raise HTTPException(status_code=422, detail="Invalid step index")
    completed = set(json.loads(evaluation.completed_steps_json or "[]"))
    if payload.done:
        completed.add(payload.step_index)
    else:
        completed.discard(payload.step_index)
    evaluation.completed_steps_json = json.dumps(sorted(completed))
    db.commit()
    db.refresh(evaluation)
    return _evaluation_out(evaluation)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.root_path:
        shutil.rmtree(project.root_path, ignore_errors=True)
    db.delete(project)
    db.commit()
