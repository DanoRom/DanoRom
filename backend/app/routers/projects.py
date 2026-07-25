import json
import re
import shutil
import zipfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import ensure_project_access, get_current_user_optional
from ..config import settings
from ..database import get_db
from ..models import Evaluation, Project, User
from ..schemas import (
    ChooseBranch,
    EvaluationOut,
    ProjectCreate,
    ProjectDetail,
    ProjectImport,
    ProjectOut,
    StepUpdate,
)
from ..services import gemini, scanner, templates

router = APIRouter(prefix="/api/projects", tags=["projects"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024

GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/tree/(?P<branch>[\w./-]+?))?/?$"
)

# GitHub's API requires a User-Agent header; the Accept header selects the v3 JSON API.
GITHUB_HEADERS = {
    "User-Agent": "developer-platform",
    "Accept": "application/vnd.github+json",
}

# Maps scanner boolean signals to the human-readable labels used in diff output.
BOOLEAN_SIGNAL_LABELS = {
    "has_readme": "readme",
    "has_tests": "tests",
    "has_ci": "CI",
    "has_docker": "Docker",
    "has_lockfile": "lockfile",
    "has_env_example": "env example",
    "has_license": "license",
}


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
        changes=json.loads(evaluation.changes_json or "[]"),
    )


def _latest_evaluation(project: Project) -> Evaluation:
    if not project.evaluations:
        raise HTTPException(status_code=409, detail="Evaluate the project first")
    return project.evaluations[0]


@router.get("", response_model=list[ProjectOut])
def list_projects(
    q: str | None = None,
    stage: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    query = db.query(Project)
    if user is not None:
        query = query.filter(or_(Project.owner_id == user.id, Project.owner_id.is_(None)))
    else:
        query = query.filter(Project.owner_id.is_(None))
    if q and q.strip():
        query = query.filter(Project.name.ilike(f"%{q.strip()}%"))
    if stage and stage.strip():
        query = query.filter(Project.stage == stage.strip())
    return query.order_by(Project.id.desc()).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Project name is required")
    project = Project(
        name=payload.name.strip(),
        description=payload.description.strip(),
        source_type="template",
        template=payload.template,
        owner_id=user.id if user else None,
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
    user: User | None = Depends(get_current_user_optional),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Upload a .zip archive of the project")

    project = Project(
        name=name.strip() or Path(file.filename).stem,
        source_type="upload",
        owner_id=user.id if user else None,
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


def parse_github_url(url: str) -> tuple[str, str, str | None]:
    """Parses a GitHub repo URL into (owner, repo, branch).

    Tolerates a trailing "/", a ".git" suffix, and a "/tree/{branch}" suffix
    (branch names may contain "/", e.g. "feature/foo"). Raises ValueError for
    anything else.
    """
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError("Not a valid GitHub repository URL")
    return match.group("owner"), match.group("repo"), match.group("branch")


def _strip_github_wrapper(incoming: Path) -> None:
    """GitHub zip archives wrap the tree in a single '{repo}-{sha}/' folder — unwrap it."""
    entries = list(incoming.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for item in inner.iterdir():
            shutil.move(str(item), str(incoming / item.name))
        inner.rmdir()


async def _resolve_github_zip_url(client: httpx.AsyncClient, owner: str, repo: str, branch: str | None) -> str:
    """Returns the codeload .zip URL for the repo, resolving the real default
    branch when none was given. Raises HTTPException with a clear message."""
    if branch:
        return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
    meta = await client.get(
        f"https://api.github.com/repos/{owner}/{repo}", headers=GITHUB_HEADERS
    )
    if meta.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {owner}/{repo} not found — check the URL, or note that private repos can't be imported.",
        )
    if meta.status_code in (403, 429):
        raise HTTPException(
            status_code=502,
            detail="GitHub rate limit reached (unauthenticated imports are limited). Try again in a few minutes.",
        )
    if meta.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub returned status {meta.status_code} for {owner}/{repo}.",
        )
    default_branch = meta.json().get("default_branch") or "main"
    return f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{default_branch}"


@router.post("/import", response_model=ProjectOut, status_code=201)
async def import_project(
    payload: ProjectImport,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Imports a public GitHub repo by URL, mirroring the .zip upload flow."""
    try:
        owner, repo, branch = parse_github_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    project = Project(
        name=payload.name.strip() or repo,
        source_type="github",
        owner_id=user.id if user else None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    incoming = settings.storage_dir / f"project-{project.id}-incoming"
    shutil.rmtree(incoming, ignore_errors=True)
    incoming.mkdir(parents=True)
    archive_path = incoming.with_suffix(".zip")

    try:
        size = 0
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                download_url = await _resolve_github_zip_url(client, owner, repo, branch)
                async with client.stream("GET", download_url, headers=GITHUB_HEADERS) as response:
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=404,
                            detail=(
                                f"Could not download {owner}/{repo} "
                                f"(archive request returned {response.status_code}). "
                                "Check the repository and branch are correct and public."
                            ),
                        )
                    with archive_path.open("wb") as out:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_UPLOAD_BYTES:
                                raise HTTPException(status_code=413, detail="Archive exceeds 50 MB limit")
                            out.write(chunk)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {exc}")
        _safe_extract(archive_path, incoming)
    except (zipfile.BadZipFile, ValueError) as exc:
        shutil.rmtree(incoming, ignore_errors=True)
        db.delete(project)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Invalid archive: {exc}")
    except HTTPException:
        shutil.rmtree(incoming, ignore_errors=True)
        db.delete(project)
        db.commit()
        raise
    finally:
        archive_path.unlink(missing_ok=True)

    _strip_github_wrapper(incoming)

    dest = _project_dir(project.id)
    shutil.rmtree(dest, ignore_errors=True)
    incoming.rename(dest)
    project.root_path = str(dest)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/reupload", response_model=ProjectOut)
async def reupload_project(
    project_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Replaces a project's files with a new archive so re-evaluation reflects real progress."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
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
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    detail = ProjectDetail.model_validate(project)
    detail.latest_evaluation = _evaluation_out(
        project.evaluations[0] if project.evaluations else None
    )
    return detail


@router.get("/{project_id}/evaluations", response_model=list[EvaluationOut])
def list_evaluations(
    project_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    return [_evaluation_out(evaluation) for evaluation in project.evaluations]


@router.get("/{project_id}/tree")
def get_project_tree(
    project_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    if not project.root_path or not Path(project.root_path).is_dir():
        raise HTTPException(status_code=409, detail="Project has no files to scan")

    scan = scanner.scan_project(project.root_path)
    return {"tree": scan["tree"], "signals": scan["signals"]}


@router.post("/{project_id}/evaluate", response_model=EvaluationOut)
def evaluate_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    if not project.root_path or not Path(project.root_path).is_dir():
        raise HTTPException(status_code=409, detail="Project has no files to scan")

    scan = scanner.scan_project(project.root_path)
    result = gemini.evaluate(scan)

    previous = project.evaluations[0] if project.evaluations else None
    previous_signals = json.loads(previous.signals_json or "{}") if previous else None
    changes = _diff_signals(previous_signals, scan["signals"])

    evaluation = Evaluation(
        project_id=project.id,
        stage=result["stage"],
        confidence=result["confidence"],
        summary=result["summary"],
        branches_json=json.dumps(result["branches"]),
        engine=result["engine"],
        signals_json=json.dumps(scan["signals"]),
        changes_json=json.dumps(changes),
    )
    project.stage = result["stage"]
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return _evaluation_out(evaluation)


def _diff_signals(previous: dict | None, current: dict) -> list[str]:
    """Compares two scanner signal dicts into a human-readable list of changes."""
    if previous is None:
        return []
    changes: list[str] = []

    for key, label in BOOLEAN_SIGNAL_LABELS.items():
        before = bool(previous.get(key))
        after = bool(current.get(key))
        if before != after:
            changes.append(f"+ {label} detected" if after else f"- {label} removed")

    file_delta = current.get("file_count", 0) - previous.get("file_count", 0)
    if file_delta:
        changes.append(f"{file_delta:+d} files")

    before_langs = set(previous.get("languages", []))
    after_langs = set(current.get("languages", []))
    for lang in sorted(after_langs - before_langs):
        changes.append(f"+{lang}")
    for lang in sorted(before_langs - after_langs):
        changes.append(f"-{lang}")

    return changes


@router.post("/{project_id}/pathway", response_model=EvaluationOut)
def choose_pathway(
    project_id: int,
    payload: ChooseBranch,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
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
def update_step(
    project_id: int,
    payload: StepUpdate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
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
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, user)
    if project.root_path:
        shutil.rmtree(project.root_path, ignore_errors=True)
    db.delete(project)
    db.commit()
