#!/usr/bin/env python3
"""Assemble COWORK-BRIEF.md: one self-contained file carrying the whole job.

    python3 build-brief.py

Embeds dr.py and rules.json verbatim so the brief works with no network and no
clone. Re-run after changing either file so the copies never drift.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent

PROSE = r"""# Black Mamba migration — complete brief

Everything needed to run this job is in this one file, including the full source
of the tool. No clone, no download, no network required.

**Give this to an agent (Cowork, Claude Code, whatever) running on the PC that
holds the drives.**

---

## 0. STOP — confirm which machine you are on

Dano has a **desktop PC** (the target), a **laptop**, and a **phone**. This
migration must run on the PC and nowhere else. Running it on the laptop would
scan the laptop's drives, upload the laptop's files, and delete them.

Write out the two files in Appendix A and B first (see §2), then:

```bash
python3 dr.py whoami
```

It prints hostname, OS, and every drive with its size. **Check those sizes
against what Dano described: roughly 1.5 TB, plus an SSD.** If you see a single
512 GB volume, you are on the laptop — stop and say so.

Then pin every later command to that hostname:

```bash
python3 dr.py auto D:/ E:/ --expect-host <hostname> --report-only
```

`--expect-host` exits non-zero rather than running on a machine whose hostname
doesn't match. Use it on every invocation from here on.

Second guard, automatic: the catalog binds itself to the machine that created it
on first scan. Copy `driveshift.db` elsewhere and every destructive command
refuses unless you pass `--rebind` deliberately. **You should never need
`--rebind` for this job. If something demands one, you are on the wrong machine.**

---

## 1. The job

Dano wants his PC emptied into a specific Google Drive folder, verified, and the
local space reclaimed — so the machine can then be wiped and rebuilt as a **home
server and home cloud storage** running his apps. You are doing the migration;
the rebuild is a separate job afterwards.

| | |
|---|---|
| Source | ~1.5 TB across local drives on this PC. There is an **SSD** plus larger storage. |
| Destination | Google Drive folder **"Black Mamba-Home-Cloud-Server"** |
| Folder ID | `1urF86RCzBsnAU31ng70V-7utkahZakOV` |
| Drive quota | 916 GB used of 5 TB → **4.08 TB free**. 1.5 TB fits. |
| Connection | 1 Gbit, CAT5e. **Upload speed unverified — measure it first.** |
| Google's cap | 750 GB per account per rolling 24h. Hard ceiling. |
| Delete policy | **Verified-then-recycle.** Chosen explicitly by Dano. |
| Target OS | Undecided. Probably Linux, possibly a VM. Keep it portable. |

### The strategy

Don't upload 1.5 TB. Upload what's left after removing what needn't move:

1. **Junk** — game libraries, package caches, build output, browser caches.
   Deleted without uploading. Typically 300–700 GB.
2. **Duplicates** — same bytes in several places. Uploaded once. 50–200 GB.
3. **Pack small files** — Google charges a round trip per file, so 200k documents
   take longer than 200 GB of video. Anything under 16 MB goes into ~4 GB tar
   bundles with a JSONL manifest. Worth 5–20x wall clock.
4. **Respect the cap** — the tool tracks a rolling 24h window and sleeps at the wall.

Expect **600 GB – 1 TB** actually crossing the wire.

### Timing

On gigabit he is **cap-bound, not bandwidth-bound**: saturating 750 GB/day needs
only ~70 Mbit/s. Expect ~4–6 hours of transfer per day, then ~18 hours idle
waiting for the window to roll. Two days elapsed, ~8–10 hours of real transfer.

**Measure upload speed before promising this.** Consumer "1 Giga" plans are often
1000 down / 50–100 up. At 100 Mbit/s up, a 750 GB day is ~17 hours and the whole
analysis changes. `fast.com/#upload` settles it in 30 seconds. CAT5e is fine — it
carries gigabit to 100 m.

---

## 2. Set up

Write the two files from the appendices to a working directory:

- **Appendix A** → `dr.py`
- **Appendix B** → `rules.json`

They must sit in the same directory. Python 3.9+ , no pip install needed.

Optionally `pip install send2trash` for native Recycle Bin support; without it the
tool uses its own trash implementation (freedesktop spec on Linux, VisualBasic
`SendToRecycleBin` on Windows, Finder on macOS). Either way, **nothing is ever
hard-deleted**.

### rclone

rclone is the only external dependency and the only thing that talks to Google.

```bash
# Linux
sudo apt install rclone || curl https://rclone.org/install.sh | sudo bash
# Windows
winget install -e --id Rclone.Rclone
# macOS
brew install rclone
```

### Get a Google API client ID first — this matters

rclone ships with credentials shared by every rclone user alive, and Google rate
limits per client ID. Your own is **3–5x faster** on a bulk move. Ten minutes:

1. <https://console.cloud.google.com/> → create a project (`blackmamba`).
2. **APIs & Services → Library** → "Google Drive API" → **Enable**.
3. **APIs & Services → OAuth consent screen** → **External**. Fill in app name and
   Dano's email for both contact fields. **Add his own Google account under Test
   users** — miss this and auth fails. Leave it in **Testing**, don't publish.
   (Testing-mode refresh tokens expire after 7 days; if the transfer runs longer,
   `rclone config reconnect blackmamba:` renews it.)
4. **Credentials → Create credentials → OAuth client ID → Desktop app.** Copy the
   client ID and client secret.

### Which Google account — check this before authorising

The destination folder is owned by **danrom1988@gmail.com**. rclone must be
authorised as *that* account, and the OAuth consent screen must list
**danrom1988@gmail.com** under **Test users**. Authorising a different Google
account is the most likely way this fails: you either get a permission error on
first upload, or files land somewhere unexpected and count against the wrong
quota.

Confirm before starting: the 5 TB of storage (916 GB used) belongs to
danrom1988@gmail.com, not another account. Google's 750 GB/day cap is also
per-account.

### Configure the remote

```bash
rclone config
```

```
n) new remote
name>            blackmamba
Storage>         drive
client_id>       <from step 4>
client_secret>   <from step 4>
scope>           1          (full access)
root_folder_id>  1urF86RCzBsnAU31ng70V-7utkahZakOV
service_account> (blank)
Edit advanced?   n
Use auto config? y on a desktop, n over SSH
Shared drive?    n
```

Targeting by **folder ID** rather than name means renaming or moving the folder in
the Drive web UI breaks nothing, and `blackmamba:` *is* that folder — nothing the
tool does can touch the rest of his Drive.

Verify:

```bash
rclone about blackmamba:
python3 dr.py doctor
```

---

## 3. Run order

### Step 1 — facts only. Deletes and uploads nothing.

```bash
python3 dr.py auto D:/ E:/ --expect-host <hostname> --report-only \
        --upstream-mbit <measured>
```

Writes `report.txt`: real payload vs redundant copies vs disposable junk, broken
down by rule and by file type.

**Show Dano this report and get his sign-off before Step 2.** He asked
specifically for these numbers. Flag anything surprising in the JUNK totals — that
is the last cheap moment to catch a misclassification.

### Step 2 — free the junk. No upload needed.

```bash
python3 dr.py reclaim --no-dupes --no-archived --yes --expect-host <hostname>
```

### Step 3 — the long haul.

```bash
python3 dr.py auto D:/ E:/ --expect-host <hostname> \
        --transfers 8 --jobs 12 --stage <path-on-SSD>
```

Resumable — kill it and re-run the same command any time. It pauses itself at the
daily cap and resumes when the window rolls. Monitor with `python3 dr.py status`.

### Step 4 — before any wipe.

```bash
python3 dr.py status         # uploaded == verified, errors zero
python3 dr.py errors         # empty
python3 dr.py backup-index   # catalog + CSV onto Drive, survives the wipe
```

Then restore three files at random and **actually open them**. Not a hash check —
open them. This is the step people skip and regret.

---

## 4. Decisions already made — don't re-litigate

- **Verified-then-recycle.** A file is reclaimable only after its MD5 is read back
  from Google and matched. Deletions go to Recycle Bin/Trash, never unlink.
- **Cloud services are ARCHIVE, not JUNK.** Dano wants OneDrive/iCloud/Dropbox
  gone. Contents are copied to Drive and verified *first*, then the local folder
  is reclaimed. Same end state, nothing lost. See §5.
- **`--stage` goes on the SSD.** Packing writes a 4 GB tarball per bundle.
- **`--jobs 12` for dedupe hashing on SSD; drop to 2 if the files being hashed
  live on a spinning disk** — concurrent reads there cause seek thrash.
- **`--transfers 8`.** Past ~8, Drive trips per-user rate limits and throughput
  goes *down*. More is not better.
- **No encryption.** `rclone crypt` is available but costs Drive-side preview and
  search. Not enabled; ask before changing that.

---

## 5. Traps that silently destroy data

**1. Online-only placeholders.** OneDrive Files On-Demand, iCloud "Optimise
Storage" and Dropbox Smart Sync leave files that look normal in the file manager
but are **0 bytes on disk**. Archiving those archives empty stubs, and nobody
notices for a year. Force a full download first:

- OneDrive — right-click the folder → *Always keep on this device*; wait for solid
  green. Or disable Files On-Demand entirely in Settings → Sync and backup → Advanced.
- iCloud — turn **off** *Optimise Storage*, then wait.
- Dropbox — right-click → *Smart Sync* → *Local*.

Verify zero placeholders remain before archiving:

```powershell
Get-ChildItem "$env:USERPROFILE\OneDrive" -Recurse -File |
  Where-Object { $_.Length -eq 0 -or $_.Attributes -match 'Offline' } |
  Measure-Object | Select-Object Count
```

**2. Sync propagation.** While a client is linked, deleting locally deletes from
that cloud. Order matters: force download → archive to Drive → verify → **unlink
the account** (OneDrive: Settings → Account → Unlink this PC; Dropbox: Preferences
→ Account → Unlink) → *then* reclaim locally → uninstall the client.

If something was already deleted with the client linked: OneDrive, Dropbox and
iCloud all keep a 30-day web-side recycle bin. Restore there first.

**3. Unconstrained rules.** A rule with no glob/ext/size/age constraint matches
every file on the drive. That bug existed in an early draft and would have marked
the whole 1.5 TB as junk. `load_rules()` now rejects such a rule outright. If you
edit `rules.json`, re-run `--report-only` and sanity-check the tier totals before
anything else.

**4. Drive alone is not a backup.** One copy is one copy. For the irreplaceable
subset (photos, documents, keys), set up restic afterwards — it dedupes, encrypts
before anything leaves the machine, and gives point-in-time snapshots.

---

## 6. How the tool works

`dr.py` is a single stdlib-only file. State lives in one SQLite catalog; every
command is resumable.

| Command | Does |
|---|---|
| `whoami` | which machine is this, what drives does it have |
| `doctor` | rclone, remote, quota, free space |
| `scan` | index the drives; prunes junk trees into single entries so a 1.5 TB scan takes minutes |
| `classify` | apply `rules.json` → SKIP / JUNK / ARCHIVE / SYNC |
| `dedupe` | size groups → head+tail hash → full hash only on collision |
| `report` | the fact sheet |
| `push` | pack → upload → verify MD5 → reclaim, in a loop |
| `status` / `errors` | progress and failures |
| `find` / `restore` | search the catalog, pull files back |
| `backup-index` | put the catalog itself on Drive |
| `auto` | all of the above, unattended |

**Tiers** (`rules.json` is ordered, first match wins, unmatched → `ARCHIVE`):

- `SKIP` — never uploaded, never deleted. System files.
- `JUNK` — deleted without uploading. Reproducible or worthless.
- `ARCHIVE` — uploaded, verified, then the local copy is reclaimed.
- `SYNC` — uploaded **and kept locally**. Hot data.

**Safety model:**

1. Only `reclaim` removes local data. `scan`/`classify`/`dedupe`/`report` are read-only.
2. `reclaim` is a dry run unless `--yes`.
3. `ARCHIVE` files reclaim only after remote MD5 matches local.
4. Duplicates reclaim only after the *kept* copy verifies.
5. Deletions go to Recycle Bin/Trash.
6. Unconstrained JUNK rules are rejected at load.
7. `push` aborts the run on the first MD5 mismatch.
8. The catalog is machine-bound; `--expect-host` adds a hostname assertion.

---

## 7. Report back to Dano

- Measured upload speed, and whether he's cap-bound or bandwidth-bound.
- From `report.txt`: total on disk, junk, duplicates, real payload.
- A realistic completion estimate.
- Anything matching `credentials-and-keys` (SSH/GPG keys, `.kdbx`, `.pem`). These
  are forced to `SYNC` and never bulk-deleted, but he should review them by hand.

## 8. Still open

- Final OS for the rebuild: bare-metal Linux, Proxmox + VMs, or stay on Windows.
  Doesn't block the migration — the catalog is one SQLite file and the remote is a
  folder ID, so everything moves over unchanged.
- Whether to encrypt the archive.

---
---

# Appendix A — `dr.py`

Write this verbatim to `dr.py`.

```python
{DR_PY}
```

---

# Appendix B — `rules.json`

Write this verbatim to `rules.json`, beside `dr.py`.

```json
{RULES_JSON}
```
"""


def main() -> int:
    dr = (HERE / "dr.py").read_text(encoding="utf-8")
    rules = (HERE / "rules.json").read_text(encoding="utf-8")

    for name, body in (("dr.py", dr), ("rules.json", rules)):
        if "```" in body:
            raise SystemExit(f"{name} contains a code fence; embedding would break")

    out = PROSE.replace("{DR_PY}", dr.rstrip()).replace("{RULES_JSON}", rules.rstrip())
    dest = HERE / "COWORK-BRIEF.md"
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest} ({len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
