<#
Starts the Developer Platform backend, frontend, and two Cloudflare quick
tunnels in ONE PowerShell window (as background jobs), wires the tunnel
URLs into NEXT_PUBLIC_API_URL and backend/.env's CORS_ORIGINS
automatically, and prints the link to share.

One-time setup before the first run:
  cd backend; python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt
  cd ..\frontend; npm install
  winget install Cloudflare.cloudflared

Usage (from the repo root):
  .\scripts\share.ps1

Keep this window open while sharing. To stop everything:
  Get-Job -Name 'dp-*' | Stop-Job -PassThru | Remove-Job -Force
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "Backend venv not found. Run once:" -ForegroundColor Red
    Write-Host "  cd backend; python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Frontend dependencies not found. Run once:" -ForegroundColor Red
    Write-Host "  cd frontend; npm install"
    exit 1
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared not found. Install it: winget install Cloudflare.cloudflared" -ForegroundColor Red
    exit 1
}

Write-Host "Cleaning up any previous run..." -ForegroundColor Cyan
Get-Job -Name "dp-*" -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job -Force
Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
# Stale .next output from a previous run can go out of sync with freshly
# pulled source and throw ENOENT/404s — always start the frontend clean.
Remove-Item -Recurse -Force (Join-Path $frontendDir ".next") -ErrorAction SilentlyContinue

function Wait-ForTunnelUrl($job, $label) {
    Write-Host "Waiting for the $label tunnel..." -ForegroundColor Cyan
    for ($i = 0; $i -lt 40; $i++) {
        $lines = Receive-Job -Job $job -Keep
        $match = $lines | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($match) { return $match.Matches[0].Value }
        Start-Sleep -Seconds 1.5
    }
    throw "$label tunnel did not come up in time. Check: Receive-Job -Name $($job.Name) -Keep"
}

Write-Host "Starting backend tunnel..." -ForegroundColor Cyan
$backendTunnelJob = Start-Job -Name "dp-backend-tunnel" -ScriptBlock { cloudflared tunnel --url http://localhost:8000 2>&1 }
$backendUrl = Wait-ForTunnelUrl $backendTunnelJob "backend"
Write-Host "Backend tunnel:  $backendUrl" -ForegroundColor Green

Write-Host "Starting frontend tunnel..." -ForegroundColor Cyan
$frontendTunnelJob = Start-Job -Name "dp-frontend-tunnel" -ScriptBlock { cloudflared tunnel --url http://localhost:3000 2>&1 }
$frontendUrl = Wait-ForTunnelUrl $frontendTunnelJob "frontend"
Write-Host "Frontend tunnel: $frontendUrl" -ForegroundColor Green

Write-Host "Updating backend/.env CORS_ORIGINS..." -ForegroundColor Cyan
$envPath = Join-Path $backendDir ".env"
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $backendDir ".env.example") $envPath }
$envLines = @(Get-Content $envPath)
$corsLine = "CORS_ORIGINS=http://localhost:3000,$frontendUrl"
if ($envLines -match "^CORS_ORIGINS=") {
    $envLines = $envLines -replace "^CORS_ORIGINS=.*", $corsLine
} else {
    $envLines += $corsLine
}
Set-Content -Path $envPath -Value $envLines

Write-Host "Starting backend..." -ForegroundColor Cyan
Start-Job -Name "dp-backend" -ScriptBlock {
    Set-Location $using:backendDir
    & $using:pythonExe dev.py
} | Out-Null

Write-Host "Starting frontend (first compile can take ~10-20s)..." -ForegroundColor Cyan
Start-Job -Name "dp-frontend" -ScriptBlock {
    Set-Location $using:frontendDir
    $env:NEXT_PUBLIC_API_URL = $using:backendUrl
    npm run dev
} | Out-Null

Start-Sleep -Seconds 8

Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host " Send this link to your friend:" -ForegroundColor Yellow
Write-Host " $frontendUrl" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Keep THIS window open. Live logs:"
Write-Host "  Receive-Job -Name dp-backend -Keep | Select-Object -Last 20"
Write-Host "  Receive-Job -Name dp-frontend -Keep | Select-Object -Last 20"
Write-Host "Stop everything:"
Write-Host "  Get-Job -Name 'dp-*' | Stop-Job -PassThru | Remove-Job -Force"
