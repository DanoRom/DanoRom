# rclone against Google Drive, for a 1.5 TB move

Three things decide how long this takes. In order of impact:

1. Whether you use your own Google API credentials.
2. Google's 750 GB/day upload ceiling.
3. How many *files* you send, not how many bytes.

Your upstream bandwidth is fourth. That surprises people.

---

## 1. Get your own API client ID (do this first)

rclone ships with a default `client_id` that is shared by every rclone user in
the world. Google rate-limits per client ID. You are queueing behind everyone.

Making your own takes about ten minutes, is free, and typically gives **3-5x
throughput** on a bulk move. It is the highest-value thing in this document.

1. Go to <https://console.cloud.google.com/> and create a project
   (name it anything — `blackmamba-migration`).
2. **APIs & Services → Library** → search "Google Drive API" → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - Fill in app name, your email for both support and developer contact
   - Scopes: skip, rclone requests what it needs
   - **Test users: add your own Google account.** Miss this and auth fails.
   - Leave it in **Testing** — do not publish. Testing-mode refresh tokens
     expire after 7 days, which is fine for a migration; if the transfer runs
     longer, just re-run `rclone config reconnect blackmamba:`.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Copy the **client ID** and **client secret**.

Feed those to `rclone config` (or the bootstrap script) when it asks.

Already configured the remote without them? Add them after the fact:

```bash
rclone config update blackmamba client_id     YOUR_ID.apps.googleusercontent.com
rclone config update blackmamba client_secret YOUR_SECRET
rclone config reconnect blackmamba:
```

---

## 2. The remote

Target the folder by **ID**, not by name. Names change; IDs don't. The ID is the
last path segment of the folder's URL:

```
https://drive.google.com/drive/folders/1urF86RCzBsnAU31ng70V-7utkahZakOV
                                       └──────── root_folder_id ────────┘
```

The resulting stanza in `rclone.conf`:

```ini
[blackmamba]
type = drive
client_id = YOUR_ID.apps.googleusercontent.com
client_secret = YOUR_SECRET
scope = drive
root_folder_id = 1urF86RCzBsnAU31ng70V-7utkahZakOV
token = {"access_token":"..."}
```

Now `blackmamba:` *is* the Black Mamba folder. Nothing the tool does can touch
the rest of your Drive.

Sanity check:

```bash
rclone about blackmamba:      # quota
rclone lsd   blackmamba:      # should list that folder's subfolders
```

---

## 3. The 750 GB/day ceiling

Google caps uploads at **750 GB per account per rolling 24 hours**. This is not
documented as a hard number by Google but it is consistent and universally
observed. Consequences:

- **1.5 TB takes at least ~2.1 days.** No amount of bandwidth changes this.
- When you hit it, uploads start failing with `uploadLimitExceeded` for the
  remainder of the window. A file already in flight completes.
- It is *rolling*, not calendar-day. `dr` models it as a rolling window and
  computes exactly when the next chunk of budget frees up.

`dr push` handles all of this: it tracks bytes sent, sleeps at the cap, and
resumes. It also passes `--drive-stop-on-upload-limit` so rclone exits cleanly
at the wall instead of burning retries against a closed door.

Doing it by hand instead:

```bash
rclone copy /source blackmamba:dest \
  --drive-stop-on-upload-limit \
  --bwlimit 8.5M                  # ~730 GB/day, paced so you never hit the wall
```

Pacing under the cap with `--bwlimit` is often better than sprinting into it —
you keep a usable connection and never lose a day.

---

## 4. Tuning flags

What `dr` uses, and why:

```
--drive-chunk-size 128M      bigger chunks = fewer round trips. Costs RAM:
                             chunk_size x transfers. 128M x 4 = 512 MB.
                             Drop to 64M on a low-RAM box; 256M if you have 16GB+.
--transfers 4                parallel files. More is not better on Drive — past
                             8 you trip per-user rate limits and go backwards.
--checkers 16                metadata comparisons are cheap, run lots.
--tpslimit 10                transactions/sec. Keeps you under the API quota.
--drive-pacer-min-sleep 10ms default is 100ms; safe to lower with your own client_id.
--drive-pacer-burst 200      allow bursts after idle.
--drive-stop-on-upload-limit exit cleanly at 750 GB rather than retry-storming.
--fast-list                  one listing pass instead of per-directory. Use on
                             sync/check, not on copy of a single file.
```

Deliberately **not** used:

- `--drive-use-trash=false` — leaves no undo on the Drive side.
- `--ignore-checksum` — the entire point is verifying the bytes arrived.
- `--transfers 32` — reliably slower on Drive, and generates 403s.

---

## 5. Why file count dominates

Every file costs a round trip regardless of size, and Google enforces per-user
requests-per-second limits. Rough shape of it:

| Payload | Files | Realistic wall clock |
|---|---|---|
| 100 GB of video | 50 | bandwidth-bound, near line rate |
| 100 GB of documents | 400,000 | hours to days, API-bound, ~10% of line rate |
| 100 GB as 25 tarballs | 25 | bandwidth-bound again |

This is why `dr` packs anything under 16 MB into ~4 GB tar bundles with a JSONL
manifest beside each one. It also keeps your Drive item count sane — Drive
enforces an item cap per account, and a sync client trying to enumerate hundreds
of thousands of items becomes unusable long before you reach it.

The manifests are uploaded alongside the bundles, so `dr find` and `dr restore`
still work file-by-file afterwards.

---

## 6. Verification

Google stores an MD5 for every uploaded binary file and serves it via the API.
So verification costs one API call and **zero bandwidth**:

```bash
rclone lsjson --hash --hash-type md5 blackmamba:bundles/bundle-00001.tar
```

`dr` compares that against the local MD5 before it will delete anything. To check
a whole tree at once:

```bash
rclone check /source blackmamba:dest --checksum --one-way
```

Google Docs/Sheets/Slides have no MD5 (they aren't really files). Irrelevant
here — you're uploading, not downloading them.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 rateLimitExceeded`, throughput collapses | shared client ID | §1 |
| `403 userRateLimitExceeded` in bursts | too many transfers | `--transfers 4 --tpslimit 10` |
| `uploadLimitExceeded` | 750 GB/day cap | wait; `dr push` does it for you |
| `storageQuotaExceeded` | Drive is full | `rclone about blackmamba:` |
| Auth dies after 7 days | consent screen in Testing mode | `rclone config reconnect blackmamba:` |
| `couldn't find root directory ID` | bad `root_folder_id` | recopy from the folder URL |
| Uploads stall near 100% | large chunk + slow line | `--drive-chunk-size 64M` |
| RAM climbing during transfer | chunk x transfers | lower either |
