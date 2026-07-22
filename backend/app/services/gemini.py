"""Evaluation engine.

Sends the scanned project tree and signals to the Google Gemini API
(free tier) and asks for the detected build stage plus branched next steps.
Falls back to a deterministic heuristic evaluator when no API key is
configured or the API call fails, so the platform always works at zero cost.
"""

import json
import re

import httpx

from ..config import settings

STAGES = [
    "ideation",
    "scaffolding",
    "feature-development",
    "testing",
    "deployment",
    "maintenance",
]

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

PROMPT_TEMPLATE = """You are a senior software architect evaluating the build stage of a project.

Project file tree:
{tree}

Detected signals:
{signals}

Classify the project's current build stage as exactly one of:
{stages}

Then propose 2-4 branched pathways of next logical development actions.
Each branch is an alternative or parallel direction with concrete steps.

Respond with ONLY valid JSON, no markdown fences, in this shape:
{{
  "stage": "<one of the stages>",
  "confidence": <integer 0-100>,
  "summary": "<2-3 sentence assessment>",
  "branches": [
    {{
      "title": "<branch title>",
      "description": "<why this branch>",
      "priority": "critical" | "recommended" | "optional",
      "steps": [
        {{"title": "<step>", "detail": "<how / what artifact to produce>"}}
      ]
    }}
  ]
}}"""


def evaluate(scan: dict) -> dict:
    """Returns {stage, confidence, summary, branches, engine}."""
    if settings.gemini_api_key:
        try:
            result = _evaluate_with_gemini(scan)
            result["engine"] = "gemini"
            return result
        except Exception:
            pass  # fall through to the free heuristic engine
    result = _heuristic_evaluate(scan)
    result["engine"] = "heuristic"
    return result


def _evaluate_with_gemini(scan: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        tree=scan["tree"][:12000],
        signals=json.dumps(scan["signals"], default=str, indent=2),
        stages=", ".join(STAGES),
    )
    url = GEMINI_URL.format(model=settings.gemini_model, key=settings.gemini_api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }
    response = httpx.post(url, json=payload, timeout=60)
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_result(text)


def _parse_result(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\s*|\s*```$", "", text)
    data = json.loads(text)
    stage = data.get("stage", "scaffolding")
    if stage not in STAGES:
        stage = "scaffolding"
    return {
        "stage": stage,
        "confidence": max(0, min(100, int(data.get("confidence", 50)))),
        "summary": str(data.get("summary", "")),
        "branches": data.get("branches", [])[:4],
    }


def _heuristic_evaluate(scan: dict) -> dict:
    s = scan["signals"]
    if s["file_count"] <= 2 and not s["dependency_files"]:
        stage = "ideation"
    elif not s["has_tests"] and s["file_count"] < 15:
        stage = "scaffolding"
    elif not s["has_tests"]:
        stage = "feature-development"
    elif not (s["has_ci"] or s["has_docker"]):
        stage = "testing"
    elif not s["has_license"] or not s["has_readme"]:
        stage = "deployment"
    else:
        stage = "maintenance"

    branch_library = {
        "ideation": [
            _branch("Define the product", "Turn the idea into a concrete plan.", "critical", [
                ("Write a README with the problem statement", "Describe what the app does and for whom."),
                ("Choose the tech stack", "Pick frontend, backend, and database that match the team's skills."),
                ("Sketch the data model", "List the core entities and their relationships."),
            ]),
            _branch("Prototype fast", "Validate the riskiest assumption first.", "recommended", [
                ("Build a throwaway spike", "A single script or page proving the core interaction works."),
                ("Demo it to one user", "Collect feedback before investing in structure."),
            ]),
        ],
        "scaffolding": [
            _branch("Solidify the skeleton", "Give the project a stable foundation.", "critical", [
                ("Set up dependency management", "Commit a lockfile so builds are reproducible."),
                ("Add project structure", "Separate source, tests, and configuration directories."),
                ("Create a .env.example", "Document required environment variables."),
            ]),
            _branch("First vertical slice", "Prove the stack end to end.", "recommended", [
                ("Implement one feature through all layers", "UI to API to database for a single use case."),
                ("Wire up local run instructions", "One command to start everything."),
            ]),
        ],
        "feature-development": [
            _branch("Add a safety net", "Features without tests rot quickly.", "critical", [
                ("Add a test framework", "pytest / vitest or equivalents for the stack."),
                ("Cover the core flows", "Write tests for the money paths first."),
            ]),
            _branch("Keep shipping features", "Momentum matters while covered by tests.", "recommended", [
                ("Prioritize the backlog", "Rank remaining features by user impact."),
                ("Ship the next feature behind small commits", "Keep changes reviewable."),
            ]),
            _branch("Refactor hotspots", "Pay down early shortcuts.", "optional", [
                ("Extract duplicated logic", "Consolidate repeated code into shared modules."),
            ]),
        ],
        "testing": [
            _branch("Automate quality gates", "Make green the default state.", "critical", [
                ("Add CI", "Run the test suite on every push (e.g. GitHub Actions free tier)."),
                ("Add a linter/formatter", "Enforce consistent style automatically."),
            ]),
            _branch("Prepare for deployment", "Get the app runnable anywhere.", "recommended", [
                ("Containerize with Docker", "Write a Dockerfile and compose file."),
                ("Externalize configuration", "All secrets and URLs via environment variables."),
            ]),
        ],
        "deployment": [
            _branch("Ship it", "Get the app in front of users.", "critical", [
                ("Deploy to a free-tier host", "Choose a platform with a genuinely free tier."),
                ("Add health checks and logging", "Know when it breaks before users do."),
            ]),
            _branch("Polish the repository", "Make the project presentable.", "recommended", [
                ("Complete the README", "Setup, usage, and screenshots."),
                ("Add a license", "Pick a permissive or proprietary license intentionally."),
            ]),
        ],
        "maintenance": [
            _branch("Operate and observe", "Keep the running system healthy.", "recommended", [
                ("Monitor errors and uptime", "Use free-tier monitoring."),
                ("Schedule dependency updates", "Patch security issues promptly."),
            ]),
            _branch("Plan the next iteration", "Growth or consolidation.", "optional", [
                ("Review user feedback", "Turn recurring requests into a roadmap."),
                ("Profile performance", "Find and fix the slowest paths."),
            ]),
        ],
    }

    summaries = {
        "ideation": "The project is essentially empty — it is at the idea stage.",
        "scaffolding": "Basic structure exists but the foundation is incomplete.",
        "feature-development": "The project has real code and dependencies but no test coverage yet.",
        "testing": "Code and tests exist; automation and packaging are the gaps.",
        "deployment": "The project is technically ready but missing release polish.",
        "maintenance": "The project shows a mature structure; focus shifts to operating and iterating.",
    }

    return {
        "stage": stage,
        "confidence": 70,
        "summary": summaries[stage],
        "branches": branch_library[stage],
    }


def _branch(title: str, description: str, priority: str, steps: list[tuple[str, str]]) -> dict:
    return {
        "title": title,
        "description": description,
        "priority": priority,
        "steps": [{"title": t, "detail": d} for t, d in steps],
    }
