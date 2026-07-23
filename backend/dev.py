"""Development server launcher.

Runs uvicorn with auto-reload while excluding the storage/ directory,
so project uploads don't restart the server mid-session.

Usage:  python dev.py
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=["storage/*"],
    )
