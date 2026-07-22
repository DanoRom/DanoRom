"""Built-in starter templates for the Start New Project flow."""

from pathlib import Path

TEMPLATES: dict[str, dict[str, str]] = {
    "blank": {
        "README.md": "# {name}\n\n{description}\n",
    },
    "nextjs-app": {
        "README.md": "# {name}\n\n{description}\n\nNext.js application.\n",
        "package.json": (
            '{{\n  "name": "{slug}",\n  "private": true,\n'
            '  "scripts": {{"dev": "next dev", "build": "next build", "start": "next start"}},\n'
            '  "dependencies": {{"next": "^15.0.0", "react": "^19.0.0", "react-dom": "^19.0.0"}}\n}}\n'
        ),
        "app/layout.jsx": (
            "export default function RootLayout({{ children }}) {{\n"
            "  return <html lang=\"en\"><body>{{children}}</body></html>;\n}}\n"
        ),
        "app/page.jsx": (
            "export default function Home() {{\n  return <main><h1>{name}</h1></main>;\n}}\n"
        ),
    },
    "fastapi-api": {
        "README.md": "# {name}\n\n{description}\n\nFastAPI service.\n",
        "requirements.txt": "fastapi\nuvicorn[standard]\n",
        "app/main.py": (
            "from fastapi import FastAPI\n\napp = FastAPI(title=\"{name}\")\n\n\n"
            "@app.get(\"/\")\ndef root():\n    return {{\"message\": \"Hello from {name}\"}}\n"
        ),
    },
    "fullstack": {
        "README.md": "# {name}\n\n{description}\n\nNext.js frontend + FastAPI backend.\n",
        "frontend/package.json": (
            '{{\n  "name": "{slug}-frontend",\n  "private": true,\n'
            '  "scripts": {{"dev": "next dev", "build": "next build"}},\n'
            '  "dependencies": {{"next": "^15.0.0", "react": "^19.0.0", "react-dom": "^19.0.0"}}\n}}\n'
        ),
        "frontend/app/page.jsx": (
            "export default function Home() {{\n  return <main><h1>{name}</h1></main>;\n}}\n"
        ),
        "backend/requirements.txt": "fastapi\nuvicorn[standard]\n",
        "backend/app/main.py": (
            "from fastapi import FastAPI\n\napp = FastAPI(title=\"{name}\")\n\n\n"
            "@app.get(\"/\")\ndef root():\n    return {{\"message\": \"Hello from {name}\"}}\n"
        ),
    },
}


def create_from_template(template: str, dest: Path, name: str, description: str) -> None:
    files = TEMPLATES.get(template, TEMPLATES["blank"])
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in name.lower()).strip("-") or "app"
    dest.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        target = dest / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            content.format(name=name, description=description, slug=slug),
            encoding="utf-8",
        )
