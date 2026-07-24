# Getting Started

A complete, from-scratch guide to running the Developer Platform on **Windows
(PowerShell)**. macOS/Linux users: the steps are identical except use
`source .venv/bin/activate` instead of `.venv\Scripts\Activate.ps1`, and `cp`
instead of `copy`.

**Prerequisites:** [Python 3.10+](https://python.org/downloads) (check "Add
Python to PATH" during install) and [Node.js 18+](https://nodejs.org). No
database or paid service is required — it runs on local SQLite with a built-in
zero-cost evaluator out of the box.

---

## Part A — One-time setup

Do this once after cloning.

### 1. Clone the repo

```powershell
cd C:\Users\<you>
git clone https://github.com/DanoRom/Developer-Platform.git
cd Developer-Platform
```

### 2. Set up the backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

> **If `Activate.ps1` errors with "running scripts is disabled":** run the
> following once, answer `Y`, then retry the activate line.
>
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. Set up the frontend

Open a **second** PowerShell window:

```powershell
cd C:\Users\<you>\Developer-Platform\frontend
npm install
```

That's the one-time setup done.

---

## Part B — Running it (every time)

### Window 1 — Backend

```powershell
cd C:\Users\<you>\Developer-Platform\backend
.venv\Scripts\Activate.ps1
python dev.py
```

Leave it running. The API is at http://localhost:8000 (interactive docs at
http://localhost:8000/docs).

### Window 2 — Frontend

```powershell
cd C:\Users\<you>\Developer-Platform\frontend
npm run dev
```

Leave it running, then open **http://localhost:3000** in your browser — that's
the app.

To stop either server, press `Ctrl+C` in its window.

---

## Part C — Sharing with a friend (optional)

To hand someone a temporary public link without deploying anywhere. Requires
`cloudflared` once: `winget install Cloudflare.cloudflared`.

Instead of Part B, from the repo root run:

```powershell
cd C:\Users\<you>\Developer-Platform
.\scripts\share.ps1
```

It starts both servers and two Cloudflare tunnels in one window, wires the URLs
together automatically, and prints a link like
`https://something.trycloudflare.com` — send that to your friend. Keep the
window open while sharing.

To stop everything:

```powershell
Get-Job -Name 'dp-*' | Stop-Job -PassThru | Remove-Job -Force
```

> The `trycloudflare.com` URL changes every time you restart, and the app only
> works while your PC and that window stay open. For a permanent link, see
> **Deploying** below.

---

## Part D — Optional extras

### Smarter AI evaluations (free Gemini key)

The platform works without any key using a built-in heuristic evaluator. For
AI-powered evaluations and the step coach, get a free key at
https://aistudio.google.com/apikey, then in `backend\.env` set:

```
GEMINI_API_KEY=your-key-here
```

Restart the backend.

### Permanent URL (free deployment)

Follow [DEPLOYMENT.md](DEPLOYMENT.md) to deploy the backend on Render, the
database on Neon, and the frontend on Vercel — all on free tiers ($0). Once
deployed you get a stable URL and can retire the tunnel workflow.

### Getting updates later

```powershell
cd C:\Users\<you>\Developer-Platform
git pull
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Dashboard says "Backend unreachable" | Window 1 isn't running — the frontend needs the API alive on port 8000. |
| `python` opens the Microsoft Store | Install Python from python.org and check "Add Python to PATH". |
| `Activate.ps1` is disabled | Run the `Set-ExecutionPolicy` command in Part A step 2. |
| Frontend shows a red hydration/error overlay mentioning a `data-*` attribute | Caused by a browser extension modifying the page; harmless. Already suppressed on `<body>`. |
| Port 3000 or 8000 "already in use" | A previous server is still running. Close its window, or the `share.ps1` script cleans these up automatically. |
