# Black Mamba: what the PC becomes

Once the drives are empty, you have a machine with 1.5 TB of local disk and a 5 TB
Google Drive behind it. The temptation is to treat Drive as the server's
filesystem. Don't. Drive is object storage wearing a filesystem costume: no
locking, no partial writes, ~200-500 ms per metadata operation, and an API quota.
Put a database or a container's state on it and you will corrupt something.

Use three tiers instead.

| Tier | Where | What lives there | Why |
|---|---|---|---|
| **0 — hot** | SSD/NVMe | OS, Docker, databases, app state, config | needs real fsync and low latency |
| **1 — warm** | the 1.5 TB disk | media library, working files, shares | served over LAN at full disk speed |
| **2 — cold** | Google Drive 5 TB | archive, plus versioned backups of tier 0 and 1 | offsite, cheap, already paid for |

The migration you just ran fills tier 2. What comes back down to tier 1 is only
what you actually use — which is the entire point of having done it.

---

## Layout

```
/srv
├── apps/            tier 0 — container state, databases, configs (SSD)
├── media/           tier 1 — the 1.5 TB disk
│   ├── movies/
│   ├── music/
│   └── photos/
├── archive/         tier 2 — read-only rclone mount of Black Mamba
└── backup/          restic cache
```

---

## Mounting the archive read-only

Read-only is deliberate: it makes it impossible for a misbehaving app to delete
your archive, and it means an accidental `rm -rf` can't propagate to Drive.

`server/rclone-archive.service` — install with:

```bash
sudo cp server/rclone-archive.service /etc/systemd/system/
sudo systemctl enable --now rclone-archive
```

The VFS cache is what makes this usable: reads are cached to local disk, so
scrubbing through an archived video doesn't re-fetch it. Size the cache to
whatever you can spare — 50 GB is a good starting point.

**Never point a database, a torrent client's active downloads, or a container's
writable layer at this mount.**

---

## Backups: Drive alone is not a backup

The migration put one copy on Drive. One copy is not a backup — delete it there
and it's gone, and ransomware on the server would happily encrypt a writable
mount.

For the irreplaceable subset (photos, documents, keys, container configs), run
**restic** to a *separate* Drive path. It gives you deduplication, encryption
before anything leaves the machine, and point-in-time snapshots:

```bash
export RESTIC_REPOSITORY=rclone:blackmamba:_restic
export RESTIC_PASSWORD_FILE=/root/.restic-pass    # back this password up offline

restic init
restic backup /srv/apps /srv/media/photos --exclude-caches
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
restic check --read-data-subset=5%                # actually test restores
```

Losing the restic password means losing the backup. Write it down somewhere
physical.

`server/restic-backup.timer` runs this nightly.

---

## Serving it

`server/docker-compose.yml` is a starting stack:

- **Samba** — LAN file shares for tier 1
- **Jellyfin** — media, reading tier 1 and the archive mount
- **Syncthing** — laptop ↔ server sync for working files, no cloud round trip
- **Caddy** — TLS reverse proxy

Deliberately absent: anything that writes to `/srv/archive`.

If you want a Google-Drive-like web UI over your own storage, add **Nextcloud** —
but give it tier 0 for its database and tier 1 for its data directory, never the
Drive mount.

---

## VM or bare metal

You said you might run this under a VM. Both work; the tradeoff is disk access.

- **Bare metal Linux** — simplest, fastest, one less layer between Docker and the
  disk. Best choice if the box is doing one job.
- **Proxmox + VMs** — worth it if you want snapshots of the whole server, or to
  run Windows alongside. Pass the 1.5 TB disk through to the storage VM rather
  than putting it on a virtual disk image.
- **Windows + WSL2 or Hyper-V** — works, but WSL2's filesystem bridge is slow and
  Docker-in-WSL2 storage is fiddly. Only pick this if the machine must stay
  Windows for something else.

Whichever you choose, `dr.py` and the rclone config move over unchanged — the
catalog is a single SQLite file and the remote is defined by a folder ID.

---

## Before you wipe the drives

Checklist. All of it, in order:

1. `python3 dr.py status` — uploaded equals verified, and errors are zero.
2. `python3 dr.py errors` — empty.
3. `python3 dr.py backup-index` — catalog and CSV are on Drive under `_index/`.
4. `rclone about blackmamba:` — used space is roughly what you expected.
5. Pull three files back at random with `dr restore` and open them. Not a hash
   check — actually open them. This is the step people skip and regret.
6. Copy `rclone.conf` and the restic password somewhere off this machine.
7. Empty the Recycle Bin only after 1-5 pass.

Then wipe.
