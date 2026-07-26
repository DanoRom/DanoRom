<#
  driveshift bootstrap - Windows 10/11

      powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1

  Installs rclone, authorises Google Drive, and pins the remote to the
  "Black Mamba-Home-Cloud-Server" folder by ID.
#>

$ErrorActionPreference = 'Stop'
$Remote   = 'blackmamba'
$FolderId = '1urF86RCzBsnAU31ng70V-7utkahZakOV'
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path

function Bold($m) { Write-Host $m -ForegroundColor Cyan }
function Info($m) { Write-Host "  $m" }

Bold 'driveshift bootstrap'
Write-Host

# --- rclone -----------------------------------------------------------------
if (Get-Command rclone -ErrorAction SilentlyContinue) {
    Info "rclone present: $((rclone version)[0])"
} else {
    Bold 'installing rclone'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Rclone.Rclone --accept-source-agreements --accept-package-agreements
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install rclone -y
    } else {
        $zip = "$env:TEMP\rclone.zip"
        $dst = "$env:LOCALAPPDATA\rclone"
        Invoke-WebRequest 'https://downloads.rclone.org/rclone-current-windows-amd64.zip' -OutFile $zip
        Expand-Archive $zip -DestinationPath $dst -Force
        $exe = (Get-ChildItem $dst -Recurse -Filter rclone.exe | Select-Object -First 1).DirectoryName
        $env:Path = "$exe;$env:Path"
        [Environment]::SetEnvironmentVariable(
            'Path', "$exe;" + [Environment]::GetEnvironmentVariable('Path','User'), 'User')
        Info "installed to $exe (added to your PATH)"
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path','User')
}

# --- python -----------------------------------------------------------------
$py = @('python','python3','py') | ForEach-Object {
    if (Get-Command $_ -ErrorAction SilentlyContinue) { $_ }
} | Select-Object -First 1
if (-not $py) {
    Bold 'installing Python'
    winget install -e --id Python.Python.3.12 --accept-source-agreements
    $py = 'python'
}
Info "python: $py"
& $py -m pip install --quiet --user send2trash 2>$null | Out-Null

# --- long paths -------------------------------------------------------------
# Without this, anything past 260 characters is invisible to the scanner, and
# deep node_modules trees blow past that constantly.
$lp = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
        -Name LongPathsEnabled -ErrorAction SilentlyContinue
if (-not $lp -or $lp.LongPathsEnabled -ne 1) {
    Bold 'enabling NTFS long path support (needs admin, reboot to take effect)'
    try {
        Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
            -Name LongPathsEnabled -Value 1
        Info 'enabled'
    } catch {
        Info 'skipped - re-run this script as Administrator to enable it'
    }
}

# --- remote -----------------------------------------------------------------
Write-Host
if ((rclone listremotes) -contains "${Remote}:") {
    Bold "remote '$Remote' already configured"
} else {
    Bold "configuring the '$Remote' remote"
    Write-Host @"

  Read docs\RCLONE.md FIRST if you have not already. Ten minutes spent creating
  your own Google API client_id is worth roughly 3-5x throughput on a move this
  size, because the default rclone client is shared by every rclone user alive
  and is permanently rate-limited.

  When 'rclone config' opens:

    n) new remote
    name>              $Remote
    Storage>           drive
    client_id>         <your own, from docs\RCLONE.md>
    client_secret>     <your own>
    scope>             1   (full access)
    root_folder_id>    $FolderId
    service_account>   (blank)
    Edit advanced?     n
    Use auto config?   y
    Shared drive?      n

"@
    Read-Host '  press enter to launch rclone config'
    rclone config
}

# --- pin the folder id ------------------------------------------------------
$dump = rclone config dump | ConvertFrom-Json
if ($dump.$Remote.root_folder_id -ne $FolderId) {
    Bold "pinning ${Remote}: to the Black Mamba folder"
    rclone config update $Remote root_folder_id $FolderId
}

# --- verify -----------------------------------------------------------------
Write-Host
Bold 'verifying'
rclone about "${Remote}:"

Write-Host
Bold 'ready'
Write-Host @"

  $py "$Here\dr.py" doctor
  $py "$Here\dr.py" scan D:\ E:\
  $py "$Here\dr.py" classify
  $py "$Here\dr.py" dedupe
  $py "$Here\dr.py" plan --upstream-mbit 100

  Run the scan from an elevated prompt so it can read every user profile.

"@
