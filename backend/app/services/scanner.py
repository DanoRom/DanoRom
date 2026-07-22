"""Scans a project directory for artifacts and dependencies.

Produces a compact scan report (file tree + detected signals) that is passed
to the evaluation engine for stage detection.
"""

import json
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".next", "__pycache__", ".venv", "venv",
    "dist", "build", "out", ".idea", ".vscode", "coverage", ".pytest_cache",
}

MAX_TREE_ENTRIES = 400
MAX_DEPTH = 6

DEPENDENCY_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "Gemfile", "composer.json",
}

TEST_MARKERS = ("test", "tests", "spec", "__tests__")
CI_MARKERS = (".github/workflows", ".gitlab-ci.yml", ".circleci", "Jenkinsfile")


def scan_project(root: str | Path) -> dict:
    root = Path(root)
    tree_lines: list[str] = []
    signals = {
        "has_readme": False,
        "has_tests": False,
        "has_ci": False,
        "has_docker": False,
        "has_lockfile": False,
        "has_env_example": False,
        "has_license": False,
        "dependency_files": [],
        "dependencies": [],
        "languages": set(),
        "file_count": 0,
    }

    def walk(directory: Path, depth: int, prefix: str) -> None:
        if depth > MAX_DEPTH or len(tree_lines) >= MAX_TREE_ENTRIES:
            return
        try:
            entries = sorted(
                directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError:
            return
        for entry in entries:
            if len(tree_lines) >= MAX_TREE_ENTRIES:
                return
            if entry.name in IGNORED_DIRS or entry.name.startswith(".git"):
                continue
            rel = entry.relative_to(root).as_posix()
            if entry.is_dir():
                tree_lines.append(f"{prefix}{entry.name}/")
                _inspect_dir(rel, signals)
                walk(entry, depth + 1, prefix + "  ")
            else:
                tree_lines.append(f"{prefix}{entry.name}")
                signals["file_count"] += 1
                _inspect_file(entry, rel, signals)

    walk(root, 0, "")
    signals["languages"] = sorted(signals["languages"])
    return {"tree": "\n".join(tree_lines), "signals": signals}


def _inspect_dir(rel: str, signals: dict) -> None:
    lowered = rel.lower()
    if any(marker in lowered.split("/") for marker in TEST_MARKERS):
        signals["has_tests"] = True
    if any(rel.startswith(marker) for marker in CI_MARKERS):
        signals["has_ci"] = True


def _inspect_file(path: Path, rel: str, signals: dict) -> None:
    name = path.name.lower()
    lowered = rel.lower()

    if name.startswith("readme"):
        signals["has_readme"] = True
    if name in ("license", "license.md", "license.txt"):
        signals["has_license"] = True
    if name in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml"):
        signals["has_docker"] = True
    if name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock"):
        signals["has_lockfile"] = True
    if name in (".env.example", ".env.sample", ".env.template"):
        signals["has_env_example"] = True
    if any(marker in lowered for marker in TEST_MARKERS):
        signals["has_tests"] = True
    if any(rel.startswith(marker) for marker in CI_MARKERS):
        signals["has_ci"] = True

    suffix = path.suffix.lower()
    lang_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".rb": "ruby", ".php": "php",
    }
    if suffix in lang_map:
        signals["languages"].add(lang_map[suffix])

    if path.name in DEPENDENCY_FILES:
        signals["dependency_files"].append(rel)
        signals["dependencies"].extend(_extract_dependencies(path))


def _extract_dependencies(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    if path.name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        deps = list(data.get("dependencies", {})) + list(data.get("devDependencies", {}))
        return deps[:40]

    if path.name == "requirements.txt":
        deps = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                deps.append(line.split("==")[0].split(">=")[0].split("[")[0].strip())
        return deps[:40]

    return []
