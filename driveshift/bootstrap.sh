#!/usr/bin/env bash
# driveshift bootstrap - Linux / macOS
#
#   bash bootstrap.sh
#
# Installs rclone, walks you through authorising Google Drive, and pins the
# remote to the "Black Mamba-Home-Cloud-Server" folder by ID.

set -euo pipefail

REMOTE="blackmamba"
FOLDER_ID="1urF86RCzBsnAU31ng70V-7utkahZakOV"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

bold "driveshift bootstrap"
echo

# --- rclone ---------------------------------------------------------------
if command -v rclone >/dev/null 2>&1; then
  info "rclone present: $(rclone version | head -1)"
else
  bold "installing rclone"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y rclone
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y rclone
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm rclone
  elif command -v brew >/dev/null 2>&1; then
    brew install rclone
  else
    curl -fsSL https://rclone.org/install.sh | sudo bash
  fi
fi

# Distro packages are often years behind; the Drive backend improves constantly.
RC_VER="$(rclone version | head -1 | grep -oE 'v[0-9]+\.[0-9]+' | tr -d v)"
if [ -n "$RC_VER" ] && [ "$(printf '%s\n1.65\n' "$RC_VER" | sort -V | head -1)" != "1.65" ]; then
  info "rclone $RC_VER is old. Consider: curl https://rclone.org/install.sh | sudo bash"
fi

# --- optional: real Recycle Bin support -----------------------------------
python3 -c 'import send2trash' 2>/dev/null \
  || pip3 install --user --quiet send2trash 2>/dev/null \
  || info "send2trash not installed; dr will use its built-in Trash implementation"

# --- remote ---------------------------------------------------------------
echo
if rclone listremotes | grep -q "^${REMOTE}:$"; then
  bold "remote '${REMOTE}' already configured"
else
  bold "configuring the '${REMOTE}' remote"
  cat <<EOF

  Read docs/RCLONE.md FIRST if you have not already. Ten minutes spent creating
  your own Google API client_id is worth roughly 3-5x throughput on a move this
  size, because the default rclone client is shared by every rclone user alive
  and is permanently rate-limited.

  When 'rclone config' opens:

    n) new remote
    name>              ${REMOTE}
    Storage>           drive
    client_id>         <your own, from docs/RCLONE.md>
    client_secret>     <your own>
    scope>             1   (full access)
    root_folder_id>    ${FOLDER_ID}
    service_account>   (blank)
    Edit advanced?     n
    Use auto config?   y on a desktop, n over SSH
    Shared drive?      n

EOF
  read -rp "  press enter to launch rclone config ... " _
  rclone config
fi

# --- pin the folder id ----------------------------------------------------
CURRENT_ID="$(rclone config dump | python3 -c "
import json,sys
try: print(json.load(sys.stdin).get('${REMOTE}',{}).get('root_folder_id',''))
except Exception: print('')
")"
if [ "$CURRENT_ID" != "$FOLDER_ID" ]; then
  bold "pinning ${REMOTE}: to the Black Mamba folder"
  rclone config update "$REMOTE" root_folder_id "$FOLDER_ID"
fi

# --- verify ---------------------------------------------------------------
echo
bold "verifying"
rclone about "${REMOTE}:" || { echo "  rclone about failed - check the remote"; exit 1; }
echo
rclone lsd "${REMOTE}:" 2>/dev/null | head -20 || true

echo
bold "ready"
cat <<EOF

  python3 "${HERE}/dr.py" doctor
  python3 "${HERE}/dr.py" scan /path/to/drive /path/to/another
  python3 "${HERE}/dr.py" classify
  python3 "${HERE}/dr.py" dedupe
  python3 "${HERE}/dr.py" plan --upstream-mbit 100

EOF
