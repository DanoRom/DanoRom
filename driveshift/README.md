# driveshift

Evacuate 1.5 TB of local drives into **Black Mamba - Home-Server-Cloud** on Google
Drive, verify every byte landed, then reclaim the space — so the PC can be wiped
and rebuilt as a home server.

---

## The idea, in one paragraph

Do not upload 1.5 TB. Upload what's *left* after you throw away what you don't
need and stop uploading the same bytes twice. On a typical PC, 30-50% of a drive
is reproducible junk (game installs, package caches, build output, browser
caches) and another 5-15% is duplicates. Then, of what genuinely has to move,
don't send it as a million small files — Google charges you a round trip per
file, so a folder of 200,000 documents takes longer to upload than a 200 GB
video. Pack the small stuff into tarballs and ship those. What's left is a
transfer that finishes in days instead of weeks, with an index you can search
afterwards.

Four levers, in the order they pay off:

| Lever | Typical saving | Why |
|---|---|---|
| Delete junk before it ever moves | 300-700 GB | Steam libraries and package caches are free to re-download |
| Deduplicate | 50-200 GB | Same file in Downloads, Desktop, and a backup folder |
| Pack small files into bundles | 5-20x wall clock | One API round trip per file is the real bottleneck |
| Respect the 750 GB/day cap | avoids a 24h lockout | Hitting it mid-transfer stalls everything for a day |

---

## Your numbers

- **Drive:** 916 GB used of 5 TB → **4.08 TB free**. 1.5 TB fits with room to spare.
- **Google's hard ceiling:** 750 GB uploaded per account per rolling 24 hours.
  1.5 TB is therefore a **~2.1 day minimum**, no matter how fast your connection is.
- **To saturate that cap you need ~70 Mbit/s sustained upstream.** Below that,
  your line is the bottleneck, not Google. At 40 Mbit/s, 1.5 TB is about 3.5 days.
- Realistically you will not upload 1.5 TB. After junk and dedupe, expect
  **600 GB - 1 TB** actually crossing the wire. `dr plan` tells you the real number
  before you commit to anything.

Nothing here needs babysitting. The transfer is resumable, it pauses itself at
the daily cap and resumes when the window rolls, and you can kill it at any point
and re-run the same command.

---

## Install

```bash
# Linux / macOS
bash bootstrap.sh
```

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
```

That installs rclone, walks you through Google authorisation, and pins the remote
to the Black Mamba folder **by folder ID** — so renaming or moving that folder in
the Drive web UI breaks nothing.

**Read [`docs/RCLONE.md`](docs/RCLONE.md) before you authorise.** Ten minutes
spent creating your own Google API client ID is worth roughly 3-5x throughput,
because rclone's default credentials are shared by every rclone user on earth and
are permanently rate-limited. On a move this size that is the difference between
two days and a week.

---

## Runbook

```bash
python3 dr.py doctor                        # rclone, remote, quota, free space
python3 dr.py scan D:/ E:/                  # index the drives (minutes, not hours)
python3 dr.py classify                      # tier everything via rules.json
python3 dr.py dedupe                        # find byte-identical copies
python3 dr.py plan --upstream-mbit 100      # what moves, how long, what it frees
```

Stop there and read the plan. It is the only output that matters before anything
is deleted or uploaded. Check the `JUNK` totals and the biggest items — if
something looks wrong, edit `rules.json` and re-run `classify --reclassify`.

Then:

```bash
python3 dr.py reclaim --no-dupes --no-archived        # dry run: junk only
python3 dr.py reclaim --no-dupes --no-archived --yes  # frees the junk immediately

python3 dr.py push --reclaim                          # the long haul
python3 dr.py backup-index                            # put the catalog on Drive
```

`push` loops: pack a bundle → upload it → verify its MD5 against Drive → delete
the local originals to the Recycle Bin → repeat. Leave it running. Check in with
`python3 dr.py status`.

Useful flags:

```
--dry-run              pack and plan, upload nothing
--max-hours 8          stop cleanly after 8 hours
--no-wait              exit at the daily cap instead of sleeping until it lifts
--compress gz          worth it for documents and source; pointless for media
--daily-cap-gb 500     leave headroom if you use the same account elsewhere
```

Afterwards, the catalog is still searchable and files are retrievable:

```bash
python3 dr.py find "tax return"
python3 dr.py restore "tax return" --to ./restored
```

---

## Tiers

`rules.json` is ordered and **first match wins**. Everything unmatched falls
through to `ARCHIVE`.

| Tier | Meaning |
|---|---|
| `SKIP` | Never uploaded, never deleted. System files — and anything already synced to a cloud. |
| `JUNK` | Deleted without uploading. Reproducible or worthless. |
| `ARCHIVE` | Uploaded, verified, then the local copy is reclaimed. The cold tier. |
| `SYNC` | Uploaded **and kept locally**. Hot data you still touch. |

Two rules exist purely as safety rails and you should not remove them:

- **`cloud-synced-already`** skips OneDrive/Dropbox/iCloud folders. Deleting a
  file from one of those locally deletes it *from that cloud too*. This is the
  single most common way people lose data during a migration.
- **`credentials-and-keys`** forces SSH keys, GPG keys, cloud credentials and
  password databases into `SYNC` so they are never bulk-deleted. Review them by
  hand before anything leaves the machine.

---

## Safety model

Nothing is deleted by accident, and deletion is always the *last* step:

1. Only `reclaim` ever removes local data. `scan`, `classify`, `dedupe` and
   `plan` are read-only.
2. `reclaim` is a **dry run unless you pass `--yes`**.
3. An `ARCHIVE` file is only reclaimable after its MD5 has been read back from
   Google and matched against the local file. Not "upload succeeded" — matched.
4. A duplicate is only reclaimable after the copy being *kept* has been verified.
5. Deletions go to the **Recycle Bin / Trash**, never a hard delete. You get a
   second undo.
6. A rules file containing a `JUNK` rule with no constraints is rejected outright
   rather than loaded — such a rule would match every file on the drive.
7. `push` aborts the whole run on the first MD5 mismatch rather than continuing.

The catalog is a single SQLite file. `backup-index` copies it and a CSV of every
uploaded file to Drive, so the index survives wiping the machine.

---

## What this deliberately does not do

- **It is not a backup.** One copy on Drive is one copy. If you delete it there,
  it is gone. For the irreplaceable subset (photos, documents, keys) run a real
  versioned backup on top — see [`docs/HOMESERVER.md`](docs/HOMESERVER.md).
- **It does not encrypt.** If you want the archive unreadable by Google, wrap the
  remote in `rclone crypt`. That costs you Drive-side preview, search, and
  dedupe, so it is a deliberate choice rather than a default.
- **It does not preserve Windows ACLs.** Packed bundles preserve POSIX
  permissions via tar; NTFS ACLs are lost. Irrelevant for archived media,
  relevant if you are archiving a system directory — so don't.

---

## Files

```
dr.py               the whole tool, stdlib only, no install step
rules.json          the classification rules; this is the file you tune
bootstrap.sh/.ps1   rclone install + Google authorisation
docs/RCLONE.md      own API credentials, tuning flags, the 750 GB/day cap
docs/HOMESERVER.md  what the PC becomes once the drives are empty
server/             compose stack + rclone mount unit for the rebuilt server
```
