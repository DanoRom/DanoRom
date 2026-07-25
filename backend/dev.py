"""Development server launcher.

Watches only the application source. Imported and uploaded projects land in
storage/ and routinely contain .py files nested many levels deep; letting the
reloader see those restarts the server in the middle of an import, which the
browser reports as a bare "Failed to fetch". Watching app/ explicitly is what
prevents that — an exclude glob like "storage/*" matches only one level down
and silently misses storage/<project>/src/deep/file.py.

Usage:  python dev.py
"""

from pathlib import Path

import uvicorn

APP_DIR = Path(__file__).resolve().parent / "app"

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(APP_DIR)],
    )
