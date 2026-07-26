# Handoff brief — Black Mamba migration

Paste this whole file into a Cowork session running **on the PC that holds the
drives**. It is written as instructions to that agent.

---

## STOP — confirm which machine you are on

Dano has a **desktop PC** (the target), a **laptop**, and a **phone**. This
migration must run on the PC and nowhere else. Running it on the laptop would
scan the laptop's drives, upload the laptop's files, and delete them.

Before anything else:

```bash
python3 dr.py whoami
```

It prints the hostname, OS, and every drive with its size. **Check the drive
sizes against what Dano described: roughly 1.5 TB plus an SSD.** If you see a
single 512 GB volume, you are on the laptop — stop and tell him.

Then note the hostname and pass it to every subsequent command:

```bash
python3 dr.py auto D:/ E:/ --expect-host <that-hostname> --report-only
```

`--expect-host` makes `dr` exit non-zero rather than run on a machine whose
hostname doesn't match. Use it on every invocation from here on.

There is a second, automatic guard: the catalog binds itself to the machine that
created it on first scan. Copy `driveshift.db` to another computer and every
destructive command refuses to run unless you pass `--rebind` explicitly. You
should never need `--rebind` for this job — if it demands one, you are on the
wrong machine.

---

## The job

Dano has a desktop PC (not his laptop) holding roughly **1.5 TB**. He wants it
emptied into a specific Google Drive folder, verified, and the local space
reclaimed — so the machine can then be wiped and rebuilt as a **home server and
home cloud storage**, running his apps.

You are doing the migration. The rebuild comes after and is a separate job.

## Hard facts

| | |
|---|---|
| Source | ~1.5 TB across local drives on this PC. There is an **SSD** plus larger storage. |
| Destination | Google Drive folder **"Black Mamba-Home-Cloud-Server"** |
| Folder ID | `1urF86RCzBsnAU31ng70V-7utkahZakOV` |
| Drive quota | 916 GB used of 5 TB → **4.08 TB free**. 1.5 TB fits. |
| Connection | 1 Gbit, CAT5e. **Upload speed is unverified — test it first.** |
| Google's cap | 750 GB uploaded per account per rolling 24h. Hard ceiling. |
| Delete policy | **Verified-then-recycle.** Chosen explicitly by Dano. |
| Target OS | Undecided. Probably Linux, possibly in a VM. Keep it portable. |

## The toolkit already exists

Don't write this from scratch. It's built, tested, and documented:

```bash
git clone -b claude/local-drive-google-migration-ofnzrx \
  https://github.com/DanoRom/DanoRom.git
cd DanoRom/driveshift
```

- `dr.py` — the whole tool. Single file, Python stdlib only, no install step.
- `rules.json` — classification rules, ordered, first match wins.
- `bootstrap.sh` / `bootstrap.ps1` — installs rclone, does Google auth, pins the
  remote to the folder ID above.
- `docs/RCLONE.md` — API credentials, tuning, the 750 GB/day cap.
- `docs/CLOUD-EVICTION.md` — **read before touching OneDrive/iCloud/Dropbox.**
- `docs/HOMESERVER.md` — the rebuild, for later.

## The strategy

Don't upload 1.5 TB. Upload what's left after removing what doesn't need to move:

1. **Junk** — game libraries, package caches, build output, browser caches.
   Deleted without uploading. Typically 300–700 GB.
2. **Duplicates** — same bytes in several places. Uploaded once. Typically 50–200 GB.
3. **Pack small files** — Google charges a round trip per file, so 200k documents
   take longer than 200 GB of video. Anything under 16 MB goes into ~4 GB tar
   bundles with a JSONL manifest. This is worth 5–20x wall clock.
4. **Respect the cap** — `dr push` tracks a rolling 24h window and sleeps at the wall.

Expect **600 GB – 1 TB** actually crossing the wire. `dr report` gives the real number.

## Timing

On gigabit he is **cap-bound, not bandwidth-bound**: saturating 750 GB/day needs
only ~70 Mbit/s. Expect ~4–6 hours of transfer per day, then ~18 hours idle
waiting for the window to roll. Two days elapsed, ~8–10 hours of real transfer.

**Verify upload speed before promising this.** Consumer "1 Giga" plans are often
1000 down / 50–100 up. At 100 Mbit/s up, a 750 GB day is ~17 hours and the
analysis changes. `fast.com/#upload`.

---

## Run order

### 0. Preflight
```bash
bash bootstrap.sh          # or: powershell -ExecutionPolicy Bypass -File bootstrap.ps1
python3 dr.py doctor
```

Bootstrap will prompt for a Google API client ID. **Get one first** — rclone's
default credentials are shared globally and permanently throttled; your own is
worth 3–5x throughput. Steps in `docs/RCLONE.md`; console at
<https://console.cloud.google.com/>. The consent screen needs Dano's own address
added under **Test users** or auth fails.

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

### 1. Facts first — deletes and uploads nothing
```bash
python3 dr.py auto D:/ E:/ --report-only --upstream-mbit <measured>
```
Produces `report.txt`: real payload vs redundant copies vs disposable junk,
broken down by rule and file type.

**Show Dano this report and get his sign-off before step 2.** He asked
specifically for these numbers. Flag anything surprising in the JUNK totals.

### 2. Free the junk — no upload needed
```bash
python3 dr.py reclaim --no-dupes --no-archived --yes
```

### 3. The long haul
```bash
python3 dr.py auto D:/ E:/ --transfers 8 --jobs 12 --stage <path-on-SSD>
```
Resumable. Kill it and re-run the same command any time. Check `dr status`.

### 4. Before any wipe
```bash
python3 dr.py status         # uploaded == verified, errors zero
python3 dr.py errors         # empty
python3 dr.py backup-index   # catalog + CSV onto Drive, survives the wipe
```
Then restore three files at random and **actually open them**. Not a hash check.

---

## Decisions already made — don't re-litigate these

- **Verified-then-recycle.** A file is reclaimable only after its MD5 is read back
  from Google and matched. Deletions go to Recycle Bin/Trash, never unlink.
- **Cloud services are ARCHIVE, not JUNK.** Dano wants OneDrive/iCloud/Dropbox
  gone. Their contents are copied to Drive and verified *first*, then the local
  folder is reclaimed. Same end state, nothing lost.
- **`--stage` goes on the SSD.** Packing writes a 4 GB tarball per bundle.
- **`--jobs 12` for dedupe hashing on SSD; drop to 2 if the files being hashed
  live on a spinning disk** — concurrent reads there cause seek thrash.
- **`--transfers 8`.** Past ~8, Drive trips per-user rate limits and throughput
  goes *down*. More is not better.

## Traps that silently destroy data

1. **Online-only placeholders.** OneDrive Files On-Demand, iCloud "Optimise
   Storage", Dropbox Smart Sync leave files that look normal but are **0 bytes on
   disk**. Archiving those archives empty stubs. Force a full download and verify
   zero placeholders remain before archiving. Procedure in `docs/CLOUD-EVICTION.md`.
2. **Sync propagation.** While a sync client is linked, deleting locally deletes
   from that cloud. **Unlink the account before reclaiming**, not after.
3. **Unconstrained rules.** A rule with no glob/ext/size/age constraint matches
   every file on the drive. This bug existed and would have marked the whole
   1.5 TB as junk; `load_rules()` now rejects such a rule outright. If you edit
   `rules.json`, re-run `--report-only` and sanity-check the tier totals.
4. **Drive alone is not a backup.** One copy is one copy. For the irreplaceable
   subset, set up restic afterwards — see `docs/HOMESERVER.md`.

## Report back to Dano

- Measured upload speed, and whether he's cap-bound or bandwidth-bound.
- From `report.txt`: total on disk, junk, duplicates, real payload.
- Realistic completion estimate.
- Anything in `credentials-and-keys` (SSH/GPG keys, `.kdbx`, `.pem`) — these are
  forced to SYNC and never bulk-deleted, but he should review them by hand.

## Still open

- Final OS for the rebuild: bare-metal Linux, Proxmox + VMs, or stay on Windows.
  Doesn't block the migration — the catalog is one SQLite file and the remote is
  a folder ID, so everything moves over unchanged.
- Whether to encrypt the archive (`rclone crypt`). Costs Drive-side preview and
  search. Not currently enabled.
