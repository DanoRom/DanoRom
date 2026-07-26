#!/usr/bin/env python3
"""
driveshift (dr) - evacuate local drives to Google Drive, then reclaim the space.

Single file, stdlib only, cross-platform (Linux / Windows / macOS).
rclone is the only external dependency and it is the only thing that talks to Google.

Pipeline:

    dr doctor      check rclone, remote, quota, free space
    dr scan        index the drives into a SQLite catalog (prunes junk trees)
    dr classify    apply rules.json -> tier: SKIP / JUNK / ARCHIVE / SYNC
    dr dedupe      find byte-identical duplicates, keep one canonical copy
    dr plan        show what would move, how long it takes, what it frees
    dr push        pack -> upload -> verify -> (optionally) reclaim, in a resumable loop
    dr status      where the operation stands
    dr find        search the catalog after the fact
    dr restore     pull a file or bundle back down

Everything is resumable. State lives in one SQLite file; kill it at any point and
re-run the same command.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE / "driveshift.db"
DEFAULT_RULES = HERE / "rules.json"

# "Black Mamba-Home-Cloud-Server" on Google Drive. Targeting the folder by ID
# rather than by name means renaming or moving it in the web UI breaks nothing.
DEFAULT_REMOTE = "blackmamba:"
ROOT_FOLDER_ID = "1urF86RCzBsnAU31ng70V-7utkahZakOV"

GiB = 1024 ** 3
MiB = 1024 ** 2

# Google enforces ~750 GB of uploads per account per rolling 24h. We stay under it.
DAILY_UPLOAD_BUDGET = 700 * GiB
ROLLING_WINDOW_SEC = 24 * 3600

# Files smaller than this get packed into tar bundles instead of uploaded
# individually. Per-file overhead on Drive is brutal and item counts are capped.
PACK_THRESHOLD = 16 * MiB
BUNDLE_TARGET = 4 * GiB

TIERS = ("SKIP", "JUNK", "ARCHIVE", "SYNC")


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #

def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n} B"


def duration(sec: float) -> str:
    sec = int(max(sec, 0))
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, _ = divmod(sec, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def say(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# catalog
# --------------------------------------------------------------------------- #

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    norm        TEXT NOT NULL,          -- lowercased, forward slashes, for matching
    root        TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- 'file' | 'dir' (dir = pruned junk tree)
    size        INTEGER NOT NULL,
    mtime       REAL NOT NULL,
    tier        TEXT,
    rule        TEXT,
    quick       TEXT,                   -- cheap head+tail hash
    full        TEXT,                   -- full content hash
    dup_of      INTEGER,                -- id of the copy we keep
    bundle      TEXT,                   -- bundle name if packed
    remote      TEXT,                   -- remote path once uploaded
    uploaded_at REAL,
    verified_at REAL,
    reclaimed_at REAL,
    err         TEXT
);
CREATE INDEX IF NOT EXISTS ix_entries_tier   ON entries(tier);
CREATE INDEX IF NOT EXISTS ix_entries_size   ON entries(size);
CREATE INDEX IF NOT EXISTS ix_entries_bundle ON entries(bundle);
CREATE INDEX IF NOT EXISTS ix_entries_quick  ON entries(quick);

CREATE TABLE IF NOT EXISTS bundles (
    name        TEXT PRIMARY KEY,
    stage_path  TEXT,
    remote      TEXT,
    bytes       INTEGER DEFAULT 0,
    count       INTEGER DEFAULT 0,
    md5         TEXT,
    state       TEXT NOT NULL,          -- planned|built|uploaded|verified|cleaned
    built_at    REAL,
    uploaded_at REAL,
    verified_at REAL,
    err         TEXT
);

CREATE TABLE IF NOT EXISTS uploads (
    ts    REAL NOT NULL,
    bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_uploads_ts ON uploads(ts);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    return db


def meta_get(db, k, default=None):
    row = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def meta_set(db, k, v):
    db.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
               (k, str(v)))


def normpath(p: str) -> str:
    return p.replace("\\", "/").lower()


# --------------------------------------------------------------------------- #
# machine binding
#
# The catalog is bound to the machine that created it. Carry driveshift.db to a
# different box - a laptop, say - and every destructive command refuses to run.
# This is the guard against pointing the tool at the wrong computer.
# --------------------------------------------------------------------------- #

def machine_fingerprint() -> dict:
    import platform
    import socket
    import uuid

    stable = ""
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            stable = Path(candidate).read_text().strip()
            break
        except OSError:
            continue
    if not stable and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                stable = winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            pass
    if not stable:
        stable = f"mac-{uuid.getnode():012x}"

    host = socket.gethostname()
    ident = hashlib.blake2b(
        f"{host}|{platform.system()}|{stable}".encode(), digest_size=8).hexdigest()
    return {
        "host": host,
        "system": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "id": ident,
    }


def local_drives() -> list:
    """Mounted volumes with their sizes - the quickest way for a human to confirm
    'yes, this is the 1.5 TB box and not my laptop'."""
    out = []
    if sys.platform == "win32":
        import string
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                try:
                    u = shutil.disk_usage(root)
                    out.append((root, u.total, u.free))
                except OSError:
                    continue
    else:
        seen = set()
        for mp in ("/", "/home", "/mnt", "/media", "/srv", "/data"):
            if not os.path.isdir(mp):
                continue
            for p in ([mp] if mp in ("/", "/home", "/srv", "/data")
                      else [os.path.join(mp, d) for d in os.listdir(mp)]):
                try:
                    u = shutil.disk_usage(p)
                except OSError:
                    continue
                if u.total in seen:
                    continue
                seen.add(u.total)
                out.append((p, u.total, u.free))
    return out


def enforce_binding(db, args, destructive: bool) -> None:
    """Bind the catalog to this machine on first use; refuse to act on any other.
    Raises SystemExit rather than returning, so no caller can ignore it."""
    fp = machine_fingerprint()
    bound_id = meta_get(db, "bound_id")
    bound_host = meta_get(db, "bound_host")

    expect = getattr(args, "expect_host", None)
    if expect and expect.lower() != fp["host"].lower():
        raise SystemExit(
            f"\nREFUSING TO RUN.\n"
            f"  --expect-host says {expect!r}\n"
            f"  this machine is  {fp['host']!r}\n"
            f"You are on the wrong computer.\n")

    if bound_id is None:
        meta_set(db, "bound_id", fp["id"])
        meta_set(db, "bound_host", fp["host"])
        meta_set(db, "bound_system", fp["system"])
        db.commit()
        say(f"catalog bound to this machine: {fp['host']} ({fp['system']}, id {fp['id']})")
        return

    if bound_id != fp["id"]:
        msg = (f"\nREFUSING TO RUN.\n"
               f"  this catalog belongs to : {bound_host} (id {bound_id})\n"
               f"  you are running on      : {fp['host']} (id {fp['id']})\n\n"
               f"driveshift.db was created on a different computer. If you copied it\n"
               f"here by mistake, delete it and start with a fresh scan. If you really\n"
               f"do mean to migrate THIS machine, re-run with --rebind.\n")
        if destructive and not getattr(args, "rebind", False):
            raise SystemExit(msg)
        if not getattr(args, "rebind", False):
            raise SystemExit(msg)
        meta_set(db, "bound_id", fp["id"])
        meta_set(db, "bound_host", fp["host"])
        db.commit()
        warn(f"rebound catalog to {fp['host']}")


def cmd_whoami(args) -> int:
    fp = machine_fingerprint()
    say("")
    say("  THIS MACHINE")
    say(f"    hostname   {fp['host']}")
    say(f"    os         {fp['system']} {fp['release']} ({fp['arch']})")
    say(f"    id         {fp['id']}")
    say("")
    say("  DRIVES")
    total = 0
    for mount, size, free in local_drives():
        total += size
        say(f"    {mount:<12} {human(size):>10} total  {human(free):>10} free")
    say(f"    {'TOTAL':<12} {human(total):>10}")
    say("")

    db_path = Path(args.db)
    if db_path.exists():
        db = open_db(db_path)
        bound = meta_get(db, "bound_host")
        bid = meta_get(db, "bound_id")
        if bound:
            match = "MATCH" if bid == fp["id"] else "*** MISMATCH ***"
            say(f"  catalog is bound to: {bound} (id {bid})  ->  {match}")
            if bid != fp["id"]:
                say("  destructive commands will refuse to run on this machine.")
    else:
        say("  no catalog yet; the first scan binds one to this machine.")
    say("")
    say("  Is this the PC with the 1.5 TB, and not the laptop? If the drive")
    say("  sizes above don't look right, stop here.")
    return 0


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #

@dataclass
class Rule:
    name: str
    tier: str
    globs: list
    exts: list
    regex: object
    min_size: int
    max_size: int
    older_days: float
    newer_days: float
    prune: bool

    @staticmethod
    def load(d: dict) -> "Rule":
        rx = d.get("regex")
        # max_size of 0 is meaningful (it means "empty files only"), so absence
        # has to be tested explicitly rather than by falsiness.
        cap = d.get("max_size")
        if d["tier"].upper() not in TIERS:
            raise ValueError(f"rule {d['name']!r}: unknown tier {d['tier']!r}")
        return Rule(
            name=d["name"],
            tier=d["tier"].upper(),
            globs=[g.lower() for g in d.get("glob", [])],
            exts=[e.lower().lstrip(".") for e in d.get("ext", [])],
            regex=re.compile(rx, re.I) if rx else None,
            min_size=int(d.get("min_size", 0)),
            max_size=int(cap) if cap is not None else (1 << 62),
            older_days=float(d.get("older_than_days", 0)),
            newer_days=float(d.get("newer_than_days", 0)),
            prune=bool(d.get("prune", False)),
        )

    def matches(self, norm: str, size: int, mtime: float, now: float) -> bool:
        if self.globs and not any(fnmatch.fnmatch(norm, g) for g in self.globs):
            return False
        if self.exts:
            ext = norm.rsplit(".", 1)[-1] if "." in norm.rsplit("/", 1)[-1] else ""
            if ext not in self.exts:
                return False
        if self.regex and not self.regex.search(norm):
            return False
        if not (self.min_size <= size <= self.max_size):
            return False
        age_days = (now - mtime) / 86400
        if self.older_days and age_days < self.older_days:
            return False
        if self.newer_days and age_days > self.newer_days:
            return False
        return True


def load_rules(path: Path) -> tuple:
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = [Rule.load(r) for r in data["rules"]]

    # A JUNK rule with no constraints at all matches every file on the drive.
    # That is never what anyone meant, so refuse to run rather than mark 1.5TB
    # for deletion.
    for r in rules:
        constrained = (r.globs or r.exts or r.regex or r.min_size
                       or r.max_size < (1 << 62) or r.older_days or r.newer_days)
        if r.tier == "JUNK" and not constrained:
            raise ValueError(
                f"rule {r.name!r} is JUNK with no glob/ext/regex/size/age constraint - "
                "it would match every file. Refusing to load rules.json.")
    return rules, data.get("default_tier", "ARCHIVE").upper()


# --------------------------------------------------------------------------- #
# rclone
# --------------------------------------------------------------------------- #

def rclone_tuning(transfers: int = 8, chunk: str = "256M") -> list:
    """Defaults are tuned for a gigabit line. On Drive, more transfers is not
    monotonically better - past ~8 you trip per-user rate limits and throughput
    goes backwards. RAM cost is chunk x transfers, so 256M x 8 = 2 GB."""
    return [
        "--drive-chunk-size", chunk,
        "--transfers", str(transfers),
        "--checkers", str(max(8, transfers * 2)),
        "--drive-pacer-min-sleep", "10ms",
        "--drive-pacer-burst", "200",
        "--tpslimit", "12",
        "--drive-stop-on-upload-limit",   # exit cleanly at the 750GB/day wall
        "--retries", "3",
        "--low-level-retries", "10",
        "--stats", "30s",
        "--stats-one-line",
    ]


def rclone(args: list, capture=True, timeout=None, extra_env=None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["rclone", *args],
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
    )


def rclone_available() -> str:
    exe = shutil.which("rclone")
    if not exe:
        return ""
    try:
        r = rclone(["version"])
        return r.stdout.splitlines()[0] if r.returncode == 0 else ""
    except Exception:
        return ""


def remote_md5(remote_path: str) -> str:
    """Ask Drive for the md5 of an uploaded object. Drive stores md5 natively,
    so this costs one API call and no bandwidth."""
    r = rclone(["lsjson", "--hash", "--hash-type", "md5", remote_path])
    if r.returncode != 0:
        return ""
    try:
        items = json.loads(r.stdout)
        return (items[0].get("Hashes") or {}).get("md5", "") if items else ""
    except Exception:
        return ""


def local_md5(path: Path, chunk=8 * MiB) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# upload budget (rolling 24h, matches how Google actually meters)
# --------------------------------------------------------------------------- #

def budget_used(db) -> int:
    cutoff = time.time() - ROLLING_WINDOW_SEC
    row = db.execute("SELECT COALESCE(SUM(bytes),0) AS b FROM uploads WHERE ts > ?",
                     (cutoff,)).fetchone()
    return int(row["b"])


def budget_remaining(db, cap: int) -> int:
    return max(0, cap - budget_used(db))


def budget_wait_seconds(db, cap: int, need: int) -> float:
    """How long until `need` bytes fit inside the rolling window."""
    cutoff = time.time() - ROLLING_WINDOW_SEC
    rows = db.execute("SELECT ts, bytes FROM uploads WHERE ts > ? ORDER BY ts",
                      (cutoff,)).fetchall()
    used = sum(r["bytes"] for r in rows)
    for r in rows:
        if cap - used >= need:
            break
        used -= r["bytes"]
        expiry = r["ts"] + ROLLING_WINDOW_SEC
        if cap - used >= need:
            return max(0.0, expiry - time.time())
    return 0.0 if cap - used >= need else ROLLING_WINDOW_SEC


def budget_record(db, nbytes: int) -> None:
    db.execute("INSERT INTO uploads(ts, bytes) VALUES(?,?)", (time.time(), nbytes))
    db.commit()


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def dir_size(path: str, cap_entries=2_000_000) -> tuple:
    """Total bytes + file count of a tree, without indexing every file."""
    total = 0
    count = 0
    stack = [path]
    while stack and count < cap_entries:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, count


def cmd_scan(args) -> int:
    db = open_db(Path(args.db))
    enforce_binding(db, args, destructive=False)
    rules, _ = load_rules(Path(args.rules))
    prune_rules = [r for r in rules if r.prune]
    skip_rules = [r for r in rules if r.tier == "SKIP"]
    now = time.time()

    roots = [str(Path(r).resolve()) for r in args.root]
    meta_set(db, "roots", json.dumps(roots))
    if args.reset:
        db.execute("DELETE FROM entries")
        db.commit()

    batch, n_files, n_pruned, total_bytes = [], 0, 0, 0
    t0 = time.time()

    def flush():
        nonlocal batch
        if batch:
            db.executemany(
                "INSERT INTO entries(path,norm,root,kind,size,mtime,tier,rule) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                "size=excluded.size, mtime=excluded.mtime", batch)
            db.commit()
            batch = []

    for root in roots:
        if not os.path.isdir(root):
            warn(f"not a directory, skipping: {root}")
            continue
        say(f"scanning {root} ...")
        stack = [root]
        while stack:
            cur = stack.pop()
            cur_norm = normpath(cur)
            # A root you named explicitly is always scanned, even if the rules
            # would otherwise class it as junk or system.
            is_root = cur == root

            if not is_root and any(r.matches(cur_norm + "/", 0, now, now) for r in skip_rules):
                continue

            hit = None if is_root else next(
                (r for r in prune_rules
                 if any(fnmatch.fnmatch(cur_norm + "/", g) for g in r.globs)), None)
            if hit:
                sz, cnt = dir_size(cur)
                batch.append((cur, cur_norm, root, "dir", sz, os.path.getmtime(cur)
                              if os.path.exists(cur) else now, hit.tier, hit.name))
                n_pruned += 1
                total_bytes += sz
                n_files += cnt
                if len(batch) >= 2000:
                    flush()
                continue

            try:
                with os.scandir(cur) as it:
                    for e in it:
                        try:
                            if e.is_symlink():
                                continue
                            if e.is_dir(follow_symlinks=False):
                                stack.append(e.path)
                                continue
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        batch.append((e.path, normpath(e.path), root, "file",
                                      st.st_size, st.st_mtime, None, None))
                        n_files += 1
                        total_bytes += st.st_size
                        if len(batch) >= 5000:
                            flush()
                            say(f"  {n_files:,} files  {human(total_bytes)}  "
                                f"({n_files / max(time.time() - t0, .01):,.0f}/s)")
            except PermissionError:
                warn(f"permission denied: {cur}")
            except OSError as exc:
                warn(f"{cur}: {exc}")

    flush()
    meta_set(db, "scanned_at", time.time())
    db.commit()
    say(f"\nindexed {n_files:,} files ({human(total_bytes)}) in {duration(time.time() - t0)}")
    say(f"pruned {n_pruned:,} junk trees into single entries (not indexed file-by-file)")
    return 0


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #

def cmd_classify(args) -> int:
    db = open_db(Path(args.db))
    rules, default_tier = load_rules(Path(args.rules))
    now = time.time()

    where = "" if args.reclassify else "WHERE tier IS NULL"
    rows = db.execute(f"SELECT id,norm,size,mtime,kind FROM entries {where}").fetchall()
    say(f"classifying {len(rows):,} entries against {len(rules)} rules ...")

    updates = []
    for r in rows:
        if r["kind"] == "dir":
            continue
        tier, name = default_tier, "default"
        for rule in rules:
            if rule.matches(r["norm"], r["size"], r["mtime"], now):
                tier, name = rule.tier, rule.name
                break
        updates.append((tier, name, r["id"]))

    db.executemany("UPDATE entries SET tier=?, rule=? WHERE id=?", updates)
    db.commit()

    say("")
    for row in db.execute(
            "SELECT tier, COUNT(*) n, SUM(size) b FROM entries GROUP BY tier ORDER BY b DESC"):
        say(f"  {row['tier'] or '-':<8} {row['n']:>10,} entries   {human(row['b'] or 0):>12}")

    say("\ntop rules by bytes:")
    for row in db.execute(
            "SELECT rule, tier, COUNT(*) n, SUM(size) b FROM entries "
            "GROUP BY rule ORDER BY b DESC LIMIT 15"):
        say(f"  {row['tier']:<8} {row['rule']:<28} {row['n']:>9,}  {human(row['b'] or 0):>12}")
    return 0


# --------------------------------------------------------------------------- #
# dedupe
# --------------------------------------------------------------------------- #

def quick_hash(path: str, size: int, edge=64 * 1024) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(path, "rb") as fh:
        h.update(fh.read(edge))
        if size > 2 * edge:
            fh.seek(-edge, os.SEEK_END)
            h.update(fh.read(edge))
    return h.hexdigest()


def full_hash(path: str, chunk=4 * MiB) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def cmd_dedupe(args) -> int:
    from concurrent.futures import ThreadPoolExecutor

    db = open_db(Path(args.db))
    min_size = args.min_size
    # Hashing is I/O bound and releases the GIL. On an SSD, 8-16 threads is a
    # large win; on a spinning disk it is a large loss, because seeking between
    # concurrent reads destroys throughput. Hence the flag.
    jobs = args.jobs
    say(f"hashing with {jobs} threads (use --jobs 2 if these files live on a spinning disk)")

    t0 = time.time()
    rows = db.execute(
        "SELECT id,path,size FROM entries WHERE kind='file' "
        "AND tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND size >= ? "
        "AND size IN (SELECT size FROM entries WHERE kind='file' "
        "  AND tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND size >= ? "
        "  GROUP BY size HAVING COUNT(*) > 1)",
        (min_size, min_size)).fetchall()
    say(f"{len(rows):,} files share a size with another file (>= {human(min_size)})")

    def q(r):
        try:
            return r["id"], quick_hash(r["path"], r["size"])
        except OSError:
            return r["id"], None

    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for eid, h in pool.map(q, rows):
            if h:
                db.execute("UPDATE entries SET quick=? WHERE id=?", (h, eid))
            done += 1
            if done % 5000 == 0:
                db.commit()
                say(f"  quick-hashed {done:,}/{len(rows):,}")
    db.commit()

    # Only files whose cheap head+tail hash collides need to be read in full.
    cand = db.execute(
        "SELECT id,path,size,mtime,quick FROM entries WHERE quick IS NOT NULL "
        "AND dup_of IS NULL AND quick IN (SELECT quick FROM entries "
        "  WHERE quick IS NOT NULL AND dup_of IS NULL "
        "  GROUP BY quick HAVING COUNT(*) > 1) ORDER BY quick").fetchall()
    say(f"{len(cand):,} need a full-content read to confirm")

    def f(r):
        try:
            return r["id"], full_hash(r["path"])
        except OSError:
            return r["id"], None

    full_by_id = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for eid, h in pool.map(f, cand):
            if h:
                full_by_id[eid] = h
                db.execute("UPDATE entries SET full=? WHERE id=?", (h, eid))
    db.commit()

    # Keep the oldest copy, then the one with the shortest path. Oldest wins
    # because it is usually the original rather than a "copy (2)".
    by_hash = {}
    for r in cand:
        h = full_by_id.get(r["id"])
        if h:
            by_hash.setdefault(h, []).append(r)

    dup_bytes = dup_count = 0
    for h, members in by_hash.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (r["mtime"], len(r["path"])))
        keeper = members[0]
        for m in members[1:]:
            db.execute("UPDATE entries SET dup_of=? WHERE id=?", (keeper["id"], m["id"]))
            dup_bytes += m["size"]
            dup_count += 1
    db.commit()

    say(f"\n{dup_count:,} duplicate files -> {human(dup_bytes)} that never has to be uploaded")
    say(f"({duration(time.time() - t0)} elapsed)")
    say("duplicates are reclaimed locally only after their canonical copy is verified on Drive")
    return 0


# --------------------------------------------------------------------------- #
# plan
# --------------------------------------------------------------------------- #

def cmd_plan(args) -> int:
    db = open_db(Path(args.db))

    def agg(sql, params=()):
        r = db.execute(sql, params).fetchone()
        return int(r["n"] or 0), int(r["b"] or 0)

    junk_n, junk_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE tier='JUNK'")
    dup_n, dup_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE dup_of IS NOT NULL")
    up_n, up_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries "
                     "WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND kind='file'")
    arc_n, arc_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries "
                       "WHERE tier='ARCHIVE' AND dup_of IS NULL AND kind='file'")
    small_n, small_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries "
                           "WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL "
                           "AND kind='file' AND size < ?", (PACK_THRESHOLD,))
    skip_n, skip_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE tier='SKIP'")

    freed = junk_b + dup_b + arc_b
    bundles = max(1, small_b // BUNDLE_TARGET) if small_b else 0
    remote_items = (up_n - small_n) + bundles

    say("=" * 68)
    say("  PLAN")
    say("=" * 68)
    say(f"  junk, delete without uploading   {junk_n:>10,}   {human(junk_b):>12}")
    say(f"  duplicates, upload once          {dup_n:>10,}   {human(dup_b):>12}")
    say(f"  to upload                        {up_n:>10,}   {human(up_b):>12}")
    say(f"    of which packed into bundles   {small_n:>10,}   {human(small_b):>12}")
    say(f"  untouched (system/SKIP)          {skip_n:>10,}   {human(skip_b):>12}")
    say("-" * 68)
    say(f"  local space reclaimed            {'':>10}   {human(freed):>12}")
    say(f"  Drive items created              {remote_items:>10,}   "
        f"(vs {up_n:,} unpacked)")
    say("=" * 68)

    up_mbit = args.upstream_mbit
    if up_mbit:
        wire_sec = up_b * 8 / (up_mbit * 1_000_000)
        cap_sec = (up_b / DAILY_UPLOAD_BUDGET) * 86400
        say(f"\n  upstream {up_mbit} Mbit/s -> {duration(wire_sec)} of wire time")
        say(f"  Google's 750GB/day ceiling   -> {duration(cap_sec)} minimum")
        say(f"  realistic wall-clock          ~{duration(max(wire_sec, cap_sec) * 1.15)}")
        say(f"  saturating the cap needs      {DAILY_UPLOAD_BUDGET * 8 / 86400 / 1e6:.0f} Mbit/s sustained")

    say("\n  biggest single items (pruned junk trees count as one):")
    rows = db.execute("""
        SELECT path, size, tier FROM entries
        WHERE tier IN ('ARCHIVE','JUNK') AND dup_of IS NULL AND size > 0
        ORDER BY size DESC LIMIT 15""").fetchall()
    for r in rows:
        say(f"    {human(r['size']):>10}  {r['tier']:<8} {r['path']}")
    return 0


def cmd_report(args) -> int:
    """The fact sheet: what is real, what is a copy, what is disposable."""
    db = open_db(Path(args.db))
    out = []

    def w(line=""):
        out.append(line)
        say(line)

    def agg(sql, params=()):
        r = db.execute(sql, params).fetchone()
        return int(r["n"] or 0), int(r["b"] or 0)

    tot_n, tot_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries")
    w("=" * 72)
    w("  WHAT IS ACTUALLY ON THESE DRIVES")
    w("=" * 72)
    w(f"  indexed {tot_n:,} entries, {human(tot_b)} total")
    w()

    w("  by tier")
    for r in db.execute("SELECT tier, COUNT(*) n, SUM(size) b FROM entries "
                        "GROUP BY tier ORDER BY b DESC"):
        pct = 100 * (r["b"] or 0) / tot_b if tot_b else 0
        w(f"    {r['tier'] or '-':<9} {r['n']:>10,}  {human(r['b'] or 0):>11}  {pct:5.1f}%")

    w()
    w("  disposable without uploading anything")
    for r in db.execute("SELECT rule, COUNT(*) n, SUM(size) b FROM entries "
                        "WHERE tier='JUNK' GROUP BY rule ORDER BY b DESC"):
        w(f"    {r['rule']:<26} {r['n']:>10,}  {human(r['b'] or 0):>11}")
    junk_n, junk_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE tier='JUNK'")
    w(f"    {'TOTAL':<26} {junk_n:>10,}  {human(junk_b):>11}")

    w()
    w("  duplicates (identical bytes, uploaded once)")
    dup_n, dup_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE dup_of IS NOT NULL")
    w(f"    {'redundant copies':<26} {dup_n:>10,}  {human(dup_b):>11}")
    w()
    w("    worst offenders:")
    for r in db.execute("""
            SELECT k.path AS keep, COUNT(*) n, SUM(d.size) b
            FROM entries d JOIN entries k ON k.id = d.dup_of
            GROUP BY d.dup_of ORDER BY b DESC LIMIT 10"""):
        w(f"      {human(r['b']):>10}  x{r['n']}  {r['keep']}")

    w()
    w("  must actually move")
    up_n, up_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries "
                     "WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND kind='file'")
    small_n, small_b = agg("SELECT COUNT(*) n, SUM(size) b FROM entries "
                           "WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL "
                           "AND kind='file' AND size < ?", (PACK_THRESHOLD,))
    w(f"    {'real payload':<26} {up_n:>10,}  {human(up_b):>11}")
    w(f"    {'  small, will be packed':<26} {small_n:>10,}  {human(small_b):>11}")
    w(f"    {'  large, sent as-is':<26} {up_n - small_n:>10,}  {human(up_b - small_b):>11}")

    w()
    w("  by file type (payload only)")
    for r in db.execute("""
            SELECT CASE WHEN INSTR(norm, '.') > 0
                   THEN LOWER(REPLACE(norm, RTRIM(norm, REPLACE(norm,'.','')), ''))
                   ELSE '(none)' END AS ext,
                   COUNT(*) n, SUM(size) b FROM entries
            WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND kind='file'
            GROUP BY ext ORDER BY b DESC LIMIT 12"""):
        w(f"    {(r['ext'] or '?')[:24]:<26} {r['n']:>10,}  {human(r['b'] or 0):>11}")

    w()
    w("=" * 72)
    w(f"  reclaimed locally    {human(junk_b + dup_b):>12}   (junk + duplicates, no upload)")
    w(f"  crosses the wire     {human(up_b):>12}")
    if tot_b:
        w(f"  you avoid uploading  {100 * (junk_b + dup_b) / tot_b:>11.1f}%   of what is on disk")
    w("=" * 72)

    if args.upstream_mbit:
        wire = up_b * 8 / (args.upstream_mbit * 1_000_000)
        cap = (up_b / DAILY_UPLOAD_BUDGET) * 86400
        w()
        w(f"  at {args.upstream_mbit:.0f} Mbit/s: {duration(wire)} of wire time")
        w(f"  Google's 750GB/day cap: {duration(cap)} minimum")
        if cap > wire:
            w(f"  -> you are CAP-bound, not bandwidth-bound. Expect ~{duration(wire)} of")
            w("     actual transfer per day, then a wait for the window to roll.")
        else:
            w("  -> you are bandwidth-bound.")

    if args.out:
        Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
        say(f"\nwritten to {args.out}")
    return 0


def cmd_auto(args) -> int:
    """Everything, unattended. This is the paste-and-walk-away command."""
    db = open_db(Path(args.db))
    enforce_binding(db, args, destructive=True)
    db.close()

    guard = []
    if args.expect_host:
        guard = ["--expect-host", args.expect_host]

    steps = [
        ("scan", ["--db", args.db, "scan", *args.root, *guard]
                 + (["--reset"] if args.reset else [])),
        ("classify", ["--db", args.db, "classify", "--reclassify"]),
        ("dedupe", ["--db", args.db, "dedupe", "--jobs", str(args.jobs)]),
        ("report", ["--db", args.db, "report", "--upstream-mbit", str(args.upstream_mbit),
                    "--out", args.out]),
    ]
    for label, argv in steps:
        say("\n" + "=" * 72)
        say(f"  {label}")
        say("=" * 72)
        rc = main(argv)
        if rc != 0:
            warn(f"{label} failed with {rc}, stopping")
            return rc

    if args.report_only:
        say("\n--report-only: stopping before anything is deleted or uploaded.")
        say(f"Read {args.out}, then re-run without --report-only.")
        return 0

    say("\n" + "=" * 72)
    say("  reclaiming junk (no upload needed)")
    say("=" * 72)
    main(["--db", args.db, "reclaim", "--no-dupes", "--no-archived", "--yes", *guard])

    say("\n" + "=" * 72)
    say("  uploading")
    say("=" * 72)
    rc = main(["--db", args.db, "push", "--remote", args.remote, "--stage", args.stage,
               "--reclaim", "--transfers", str(args.transfers), *guard])
    main(["--db", args.db, "backup-index", "--remote", args.remote])
    return rc


# --------------------------------------------------------------------------- #
# push: pack -> upload -> verify -> reclaim
# --------------------------------------------------------------------------- #

def free_space(path: str) -> int:
    return shutil.disk_usage(path).free


def build_bundle(db, stage: Path, remote_prefix: str, compress: str) -> dict | None:
    """Pack the next group of small files into one tar. Grouped by directory so
    a restore of one folder touches one bundle."""
    row = db.execute("""
        SELECT id, path, size FROM entries
        WHERE kind='file' AND tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL
          AND bundle IS NULL AND uploaded_at IS NULL AND size < ?
        ORDER BY norm LIMIT 1""", (PACK_THRESHOLD,)).fetchone()
    if not row:
        return None

    picked, total = [], 0
    cursor = db.execute("""
        SELECT id, path, size FROM entries
        WHERE kind='file' AND tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL
          AND bundle IS NULL AND uploaded_at IS NULL AND size < ?
        ORDER BY norm""", (PACK_THRESHOLD,))
    for r in cursor:
        if total + r["size"] > BUNDLE_TARGET and picked:
            break
        picked.append(r)
        total += r["size"]
    if not picked:
        return None

    seq = int(meta_get(db, "bundle_seq", "0")) + 1
    meta_set(db, "bundle_seq", seq)
    db.commit()

    ext = {"none": ".tar", "gz": ".tar.gz", "bz2": ".tar.bz2", "xz": ".tar.xz"}[compress]
    name = f"bundle-{seq:05d}{ext}"
    out = stage / name
    manifest = stage / f"{name}.manifest.jsonl"

    need = int(total * 1.05) + 64 * MiB
    if free_space(str(stage)) < need:
        raise RuntimeError(
            f"stage dir {stage} needs {human(need)} free, has {human(free_space(str(stage)))}. "
            "Point --stage at a drive with headroom, or lower BUNDLE_TARGET.")

    mode = {"none": "w", "gz": "w:gz", "bz2": "w:bz2", "xz": "w:xz"}[compress]
    say(f"  packing {name}: {len(picked):,} files, {human(total)}")
    written = 0
    with tarfile.open(out, mode) as tf, open(manifest, "w", encoding="utf-8") as mf:
        for r in picked:
            try:
                arc = r["path"].replace("\\", "/").lstrip("/").replace(":", "")
                tf.add(r["path"], arcname=arc, recursive=False)
                mf.write(json.dumps({"id": r["id"], "path": r["path"],
                                     "arcname": arc, "size": r["size"]}) + "\n")
                db.execute("UPDATE entries SET bundle=? WHERE id=?", (name, r["id"]))
                written += r["size"]
            except (OSError, ValueError) as exc:
                db.execute("UPDATE entries SET err=? WHERE id=?", (str(exc), r["id"]))

    size_on_disk = out.stat().st_size
    db.execute("INSERT INTO bundles(name, stage_path, remote, bytes, count, state, built_at) "
               "VALUES(?,?,?,?,?,'built',?)",
               (name, str(out), f"{remote_prefix}/bundles/{name}",
                size_on_disk, len(picked), time.time()))
    db.commit()
    say(f"    -> {human(size_on_disk)} on disk"
        + (f" ({100 * size_on_disk / max(written, 1):.0f}% of raw)" if compress != "none" else ""))
    return {"name": name, "path": out, "manifest": manifest, "bytes": size_on_disk}


def upload_file(local: Path, remote: str, dry: bool, tuning: list | None = None) -> tuple:
    if dry:
        return True, "dry-run"
    args = ["copyto", str(local), remote, *(tuning if tuning is not None else rclone_tuning())]
    r = rclone(args, capture=True, timeout=None)
    if r.returncode == 0:
        return True, ""
    tail = (r.stderr or "").strip().splitlines()[-3:]
    return False, " | ".join(tail) or f"rclone exit {r.returncode}"


def is_quota_error(msg: str) -> bool:
    m = msg.lower()
    return any(s in m for s in ("uploadlimitexceeded", "quota", "userratelimitexceeded",
                                "stop-on-upload-limit", "storagequotaexceeded"))


def cmd_push(args) -> int:
    db = open_db(Path(args.db))
    enforce_binding(db, args, destructive=True)
    stage = Path(args.stage).resolve()
    stage.mkdir(parents=True, exist_ok=True)
    remote_prefix = args.remote.rstrip("/")
    cap = int(args.daily_cap_gb * GiB)

    if not args.dry_run and not rclone_available():
        warn("rclone not found on PATH. Run `dr doctor` or bootstrap first.")
        return 2

    tuning = rclone_tuning(args.transfers, args.chunk)
    deadline = time.time() + args.max_hours * 3600 if args.max_hours else None
    moved = 0

    while True:
        if deadline and time.time() > deadline:
            say("\ntime budget reached, stopping cleanly (re-run to continue)")
            break

        # 1. large files go up on their own
        big = db.execute("""
            SELECT id, path, size FROM entries
            WHERE kind='file' AND tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL
              AND size >= ? AND uploaded_at IS NULL AND (err IS NULL OR err='')
            ORDER BY size DESC LIMIT 1""", (PACK_THRESHOLD,)).fetchone()

        if big:
            wait = budget_wait_seconds(db, cap, min(big["size"], cap))
            if wait > 0:
                say(f"\ndaily upload budget spent ({human(budget_used(db))}/{human(cap)}). "
                    f"Next window in {duration(wait)}.")
                if args.no_wait:
                    break
                time.sleep(min(wait, 900))
                continue

            rel = relative_remote(db, big["path"])
            remote = f"{remote_prefix}/files/{rel}"
            say(f"up {human(big['size']):>10}  {big['path']}")
            ok, err = upload_file(Path(big["path"]), remote, args.dry_run, tuning)
            if ok:
                db.execute("UPDATE entries SET uploaded_at=?, remote=? WHERE id=?",
                           (time.time(), remote, big["id"]))
                budget_record(db, big["size"])
                moved += big["size"]
                if args.verify:
                    verify_entry(db, big["id"], Path(big["path"]), remote, args.dry_run)
            else:
                if is_quota_error(err):
                    say(f"\nGoogle says: daily upload limit. Pausing. ({err[:120]})")
                    db.execute("INSERT INTO uploads(ts,bytes) VALUES(?,?)", (time.time(), cap))
                    db.commit()
                    if args.no_wait:
                        break
                    continue
                db.execute("UPDATE entries SET err=? WHERE id=?", (err[:500], big["id"]))
            db.commit()
            continue

        # 2. otherwise pack + ship a bundle
        pending = db.execute(
            "SELECT name, stage_path, remote, bytes FROM bundles "
            "WHERE state='built' ORDER BY name LIMIT 1").fetchone()

        if not pending:
            try:
                b = build_bundle(db, stage, remote_prefix, args.compress)
            except RuntimeError as exc:
                warn(str(exc))
                return 3
            if not b:
                say("\nnothing left to upload.")
                break
            pending = db.execute(
                "SELECT name, stage_path, remote, bytes FROM bundles WHERE name=?",
                (b["name"],)).fetchone()

        wait = budget_wait_seconds(db, cap, min(pending["bytes"], cap))
        if wait > 0:
            say(f"\ndaily upload budget spent ({human(budget_used(db))}/{human(cap)}). "
                f"Next window in {duration(wait)}.")
            if args.no_wait:
                break
            time.sleep(min(wait, 900))
            continue

        say(f"up {human(pending['bytes']):>10}  {pending['name']}")
        ok, err = upload_file(Path(pending["stage_path"]), pending["remote"], args.dry_run, tuning)
        if not ok:
            if is_quota_error(err):
                say("\nGoogle says: daily upload limit. Pausing.")
                db.execute("INSERT INTO uploads(ts,bytes) VALUES(?,?)", (time.time(), cap))
                db.commit()
                if args.no_wait:
                    break
                continue
            db.execute("UPDATE bundles SET err=? WHERE name=?", (err[:500], pending["name"]))
            db.commit()
            warn(f"{pending['name']}: {err}")
            return 4

        # manifest rides along so the index survives a wipe
        mpath = Path(pending["stage_path"] + ".manifest.jsonl")
        if mpath.exists():
            upload_file(mpath, f"{remote_prefix}/manifests/{mpath.name}", args.dry_run, tuning)

        db.execute("UPDATE bundles SET state='uploaded', uploaded_at=? WHERE name=?",
                   (time.time(), pending["name"]))
        budget_record(db, pending["bytes"])
        moved += pending["bytes"]

        verified = True
        if args.verify and not args.dry_run:
            lm = local_md5(Path(pending["stage_path"]))
            rm = remote_md5(pending["remote"])
            verified = bool(rm) and lm == rm
            if verified:
                db.execute("UPDATE bundles SET state='verified', md5=?, verified_at=? "
                           "WHERE name=?", (lm, time.time(), pending["name"]))
                db.execute("UPDATE entries SET uploaded_at=?, verified_at=?, remote=? "
                           "WHERE bundle=?",
                           (time.time(), time.time(), pending["remote"], pending["name"]))
                say(f"    verified md5 {lm[:12]}...")
            else:
                db.execute("UPDATE bundles SET err=? WHERE name=?",
                           (f"md5 mismatch local={lm} remote={rm}", pending["name"]))
                db.commit()
                warn(f"{pending['name']}: md5 mismatch, NOT deleting anything")
                return 5
        else:
            db.execute("UPDATE entries SET uploaded_at=?, remote=? WHERE bundle=?",
                       (time.time(), pending["remote"], pending["name"]))

        if verified and not args.keep_stage:
            for p in (Path(pending["stage_path"]), mpath):
                try:
                    p.unlink()
                except OSError:
                    pass
            db.execute("UPDATE bundles SET state='cleaned' WHERE name=?", (pending["name"],))
        db.commit()

        if args.reclaim and verified:
            reclaim_bundle(db, pending["name"], args.dry_run)

    say(f"\nmoved {human(moved)} this run. Budget used in the last 24h: "
        f"{human(budget_used(db))} / {human(cap)}")
    if args.reclaim:
        cmd_status(argparse.Namespace(db=args.db))
    return 0


def relative_remote(db, path: str) -> str:
    """Map a local absolute path to a stable remote path."""
    p = path.replace("\\", "/")
    p = re.sub(r"^([A-Za-z]):/", r"\1/", p)      # C:/x -> C/x
    return p.lstrip("/")


def verify_entry(db, eid: int, local: Path, remote: str, dry: bool) -> bool:
    if dry:
        return True
    lm = local_md5(local)
    rm = remote_md5(remote)
    if rm and lm == rm:
        db.execute("UPDATE entries SET verified_at=?, full=? WHERE id=?",
                   (time.time(), lm, eid))
        db.commit()
        return True
    db.execute("UPDATE entries SET err=? WHERE id=?",
               (f"md5 mismatch local={lm} remote={rm}", eid))
    db.commit()
    warn(f"md5 mismatch: {local}")
    return False


# --------------------------------------------------------------------------- #
# reclaim (the only thing that removes local data)
# --------------------------------------------------------------------------- #

def to_trash(path: str) -> tuple:
    """Recycle Bin / freedesktop Trash / macOS Trash. Never a hard delete."""
    try:
        from send2trash import send2trash  # type: ignore
        send2trash(path)
        return True, ""
    except ImportError:
        pass
    except Exception as exc:
        return False, str(exc)

    try:
        if sys.platform == "win32":
            ps = (
                "Add-Type -AssemblyName Microsoft.VisualBasic; "
                f"$p='{path}'; "
                "if (Test-Path -LiteralPath $p -PathType Container) "
                "{[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory("
                "$p,'OnlyErrorDialogs','SendToRecycleBin')} else "
                "{[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
                "$p,'OnlyErrorDialogs','SendToRecycleBin')}"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True)
            return r.returncode == 0, (r.stderr or "").strip()[:200]

        if sys.platform == "darwin":
            script = f'tell application "Finder" to delete POSIX file "{path}"'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return r.returncode == 0, (r.stderr or "").strip()[:200]

        # freedesktop.org trash spec
        home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        tdir = home / "Trash"
        (tdir / "files").mkdir(parents=True, exist_ok=True)
        (tdir / "info").mkdir(parents=True, exist_ok=True)
        src = Path(path)
        base, n = src.name, 0
        dest = tdir / "files" / base
        while dest.exists():
            n += 1
            dest = tdir / "files" / f"{base}.{n}"
        info = tdir / "info" / f"{dest.name}.trashinfo"
        info.write_text(
            "[Trash Info]\n"
            f"Path={src.resolve()}\n"
            f"DeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n",
            encoding="utf-8")
        shutil.move(str(src), str(dest))
        return True, ""
    except Exception as exc:
        return False, str(exc)[:200]


def reclaim_rows(db, rows, dry: bool, label: str) -> int:
    freed, failed = 0, 0
    for r in rows:
        if dry:
            freed += r["size"]
            continue
        if not os.path.exists(r["path"]):
            db.execute("UPDATE entries SET reclaimed_at=? WHERE id=?", (time.time(), r["id"]))
            continue
        ok, err = to_trash(r["path"])
        if ok:
            db.execute("UPDATE entries SET reclaimed_at=? WHERE id=?", (time.time(), r["id"]))
            freed += r["size"]
        else:
            failed += 1
            db.execute("UPDATE entries SET err=? WHERE id=?", (f"trash: {err}", r["id"]))
    db.commit()
    say(f"  {label}: {'would free' if dry else 'freed'} {human(freed)}"
        + (f"  ({failed} failed)" if failed else ""))
    return freed


def reclaim_bundle(db, bundle: str, dry: bool) -> int:
    rows = db.execute(
        "SELECT id, path, size FROM entries WHERE bundle=? AND verified_at IS NOT NULL "
        "AND reclaimed_at IS NULL", (bundle,)).fetchall()
    return reclaim_rows(db, rows, dry, f"reclaim {bundle}")


def cmd_reclaim(args) -> int:
    db = open_db(Path(args.db))
    enforce_binding(db, args, destructive=True)
    dry = args.dry_run
    say("reclaim: nothing is touched unless it is JUNK, a verified duplicate, "
        "or verified on Drive.\n")
    total = 0

    if args.junk:
        rows = db.execute(
            "SELECT id, path, size FROM entries WHERE tier='JUNK' AND reclaimed_at IS NULL"
        ).fetchall()
        total += reclaim_rows(db, rows, dry, f"junk ({len(rows):,} entries)")

    if args.dupes:
        rows = db.execute("""
            SELECT d.id, d.path, d.size FROM entries d
            JOIN entries k ON k.id = d.dup_of
            WHERE d.dup_of IS NOT NULL AND d.reclaimed_at IS NULL
              AND k.verified_at IS NOT NULL""").fetchall()
        total += reclaim_rows(db, rows, dry, f"duplicates ({len(rows):,} entries)")

    if args.archived:
        rows = db.execute(
            "SELECT id, path, size FROM entries WHERE tier='ARCHIVE' AND kind='file' "
            "AND verified_at IS NOT NULL AND reclaimed_at IS NULL AND dup_of IS NULL"
        ).fetchall()
        total += reclaim_rows(db, rows, dry, f"verified archive ({len(rows):,} entries)")

    say(f"\n{'would free' if dry else 'freed'} {human(total)} total")
    if dry:
        say("re-run with --yes to actually move these to the Recycle Bin / Trash")
    return 0


# --------------------------------------------------------------------------- #
# status / doctor / find / restore
# --------------------------------------------------------------------------- #

def cmd_status(args) -> int:
    db = open_db(Path(args.db))

    def one(sql, params=()):
        r = db.execute(sql, params).fetchone()
        return int(r["n"] or 0), int(r["b"] or 0)

    tot_n, tot_b = one("SELECT COUNT(*) n, SUM(size) b FROM entries "
                       "WHERE tier IN ('ARCHIVE','SYNC') AND dup_of IS NULL AND kind='file'")
    up_n, up_b = one("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE uploaded_at IS NOT NULL")
    ver_n, ver_b = one("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE verified_at IS NOT NULL")
    rec_n, rec_b = one("SELECT COUNT(*) n, SUM(size) b FROM entries WHERE reclaimed_at IS NOT NULL")
    err_n, _ = one("SELECT COUNT(*) n, 0 b FROM entries WHERE err IS NOT NULL AND err <> ''")

    pct = 100 * up_b / tot_b if tot_b else 0
    bar_w = 40
    filled = int(bar_w * pct / 100)
    say("")
    say(f"  [{'#' * filled}{'.' * (bar_w - filled)}] {pct:5.1f}%")
    say(f"  uploaded   {human(up_b):>12} / {human(tot_b):<12} ({up_n:,} entries)")
    say(f"  verified   {human(ver_b):>12}                  ({ver_n:,})")
    say(f"  reclaimed  {human(rec_b):>12}                  ({rec_n:,})")
    if err_n:
        say(f"  errors     {err_n:,}  (dr errors to list them)")

    used = budget_used(db)
    say(f"\n  24h upload budget: {human(used)} / {human(DAILY_UPLOAD_BUDGET)}")
    left = tot_b - up_b
    if left > 0:
        say(f"  remaining {human(left)} -> "
            f"{duration((left / DAILY_UPLOAD_BUDGET) * 86400)} minimum at Google's cap")

    rows = db.execute("SELECT state, COUNT(*) n, SUM(bytes) b FROM bundles GROUP BY state")
    bs = list(rows)
    if bs:
        say("\n  bundles: " + ", ".join(f"{r['state']}={r['n']}" for r in bs))
    return 0


def cmd_errors(args) -> int:
    db = open_db(Path(args.db))
    for r in db.execute("SELECT path, err FROM entries WHERE err IS NOT NULL AND err<>'' "
                        "LIMIT ?", (args.limit,)):
        say(f"  {r['path']}\n      {r['err']}")
    for r in db.execute("SELECT name, err FROM bundles WHERE err IS NOT NULL AND err<>''"):
        say(f"  [bundle] {r['name']}\n      {r['err']}")
    return 0


def cmd_doctor(args) -> int:
    ok = True
    ver = rclone_available()
    say(f"  rclone            {'OK  ' + ver if ver else 'MISSING'}")
    ok &= bool(ver)

    if ver:
        remote_name = args.remote.split(":")[0]
        r = rclone(["listremotes"])
        remotes = [x.strip().rstrip(":") for x in (r.stdout or "").splitlines()]
        found = remote_name in remotes
        say(f"  remote '{remote_name}'  {'OK' if found else 'NOT CONFIGURED  (rclone config)'}")
        ok &= found
        if found:
            r = rclone(["about", f"{remote_name}:", "--json"], timeout=60)
            try:
                a = json.loads(r.stdout)
                total, used = a.get("total", 0), a.get("used", 0)
                say(f"  Drive quota       {human(used)} used / {human(total)} "
                    f"({human(total - used)} free)")
            except Exception:
                warn("could not read quota (rclone about failed)")

        cfg = rclone(["config", "dump"])
        try:
            dump = json.loads(cfg.stdout or "{}")
            entry = dump.get(remote_name, {})
            if entry.get("type") == "drive" and not entry.get("client_id"):
                warn("this remote uses rclone's SHARED Google API client. Expect heavy "
                     "throttling on a 1.5TB move. See docs/RCLONE.md to create your own "
                     "client_id (10 minutes, free, roughly 3-5x faster).")
        except Exception:
            pass

    stage = Path(args.stage)
    if stage.exists():
        say(f"  stage {stage}      {human(free_space(str(stage)))} free")
        if free_space(str(stage)) < 2 * BUNDLE_TARGET:
            warn(f"stage needs at least {human(2 * BUNDLE_TARGET)} free for packing")
    else:
        say(f"  stage {stage}      will be created")

    say(f"  python            {sys.version.split()[0]}")
    try:
        import send2trash  # noqa: F401
        say("  send2trash        OK")
    except ImportError:
        say("  send2trash        not installed (built-in trash fallback will be used)")
    return 0 if ok else 1


def cmd_find(args) -> int:
    db = open_db(Path(args.db))
    like = f"%{args.pattern.lower()}%"
    rows = db.execute(
        "SELECT path, size, tier, bundle, remote, reclaimed_at FROM entries "
        "WHERE norm LIKE ? ORDER BY size DESC LIMIT ?", (like, args.limit)).fetchall()
    for r in rows:
        where = r["bundle"] or r["remote"] or "(local only)"
        gone = " [reclaimed]" if r["reclaimed_at"] else ""
        say(f"  {human(r['size']):>10}  {r['tier']:<8} {r['path']}{gone}\n"
            f"              -> {where}")
    say(f"\n{len(rows)} match(es)")
    return 0


def cmd_restore(args) -> int:
    db = open_db(Path(args.db))
    dest = Path(args.to).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    rows = db.execute(
        "SELECT path, bundle, remote FROM entries WHERE norm LIKE ? LIMIT 200",
        (f"%{args.pattern.lower()}%",)).fetchall()
    if not rows:
        say("no match in the catalog")
        return 1

    bundles = {r["bundle"] for r in rows if r["bundle"]}
    singles = [r for r in rows if not r["bundle"] and r["remote"]]

    for b in bundles:
        br = db.execute("SELECT remote FROM bundles WHERE name=?", (b,)).fetchone()
        if not br:
            continue
        local = dest / b
        say(f"pulling {b} ...")
        r = rclone(["copyto", br["remote"], str(local), "--progress"], capture=False)
        if r.returncode != 0:
            warn(f"failed to pull {b}")
            continue
        wanted = {x["path"] for x in rows if x["bundle"] == b}
        with tarfile.open(local) as tf:
            members = []
            for m in tf.getmembers():
                for w in wanted:
                    if m.name in w.replace("\\", "/").lstrip("/").replace(":", ""):
                        members.append(m)
                        break
            tf.extractall(dest / "extracted", members=members or None)
        say(f"  extracted {len(members)} file(s) to {dest / 'extracted'}")
        if not args.keep_bundle:
            local.unlink(missing_ok=True)

    for s in singles:
        out = dest / Path(s["path"]).name
        say(f"pulling {s['remote']} ...")
        rclone(["copyto", s["remote"], str(out), "--progress"], capture=False)

    return 0


def cmd_backup_index(args) -> int:
    """The catalog is what makes the archive navigable after the drive is wiped.
    Put a copy on Drive."""
    db_path = Path(args.db)
    db = open_db(db_path)
    csv_path = db_path.with_suffix(".catalog.csv")
    import csv as _csv
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["path", "size", "mtime", "tier", "bundle", "remote", "md5"])
        for r in db.execute("SELECT path,size,mtime,tier,bundle,remote,full FROM entries "
                            "WHERE uploaded_at IS NOT NULL"):
            w.writerow([r["path"], r["size"], r["mtime"], r["tier"],
                        r["bundle"], r["remote"], r["full"]])
    prefix = args.remote.rstrip("/")
    for p in (db_path, csv_path):
        ok, err = upload_file(p, f"{prefix}/_index/{p.name}", args.dry_run)
        say(f"  {'OK ' if ok else 'FAIL'} {p.name} -> {prefix}/_index/{p.name} {err}")
    return 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dr", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="index drives into the catalog")
    s.add_argument("root", nargs="+")
    s.add_argument("--rules", default=str(DEFAULT_RULES))
    s.add_argument("--reset", action="store_true", help="wipe the catalog first")
    s.add_argument("--expect-host", default=None,
                   help="refuse to run unless the hostname matches. Use this to "
                        "guarantee you are on the PC and not the laptop")
    s.add_argument("--rebind", action="store_true",
                   help="allow a catalog created on another machine to be reused here")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("classify", help="apply rules -> tiers")
    s.add_argument("--rules", default=str(DEFAULT_RULES))
    s.add_argument("--reclassify", action="store_true", help="re-tier everything")
    s.set_defaults(fn=cmd_classify)

    s = sub.add_parser("dedupe", help="find byte-identical duplicates")
    s.add_argument("--min-size", type=int, default=1 * MiB)
    s.add_argument("--jobs", type=int, default=12,
                   help="hashing threads. 12+ on SSD/NVMe, 2 on a spinning disk")
    s.set_defaults(fn=cmd_dedupe)

    s = sub.add_parser("report", help="the fact sheet: real data vs copies vs junk")
    s.add_argument("--upstream-mbit", type=float, default=0)
    s.add_argument("--out", default="", help="also write the report to this file")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("auto", help="scan+classify+dedupe+report+reclaim+upload, unattended")
    s.add_argument("root", nargs="+")
    s.add_argument("--remote", default=DEFAULT_REMOTE)
    s.add_argument("--stage", default=str(HERE / "stage"))
    s.add_argument("--jobs", type=int, default=12)
    s.add_argument("--transfers", type=int, default=8)
    s.add_argument("--upstream-mbit", type=float, default=1000)
    s.add_argument("--out", default=str(HERE / "report.txt"))
    s.add_argument("--reset", action="store_true")
    s.add_argument("--report-only", action="store_true",
                   help="stop after the report; delete and upload nothing")
    s.add_argument("--expect-host", default=None,
                   help="refuse to run unless the hostname matches. Use this to "
                        "guarantee you are on the PC and not the laptop")
    s.add_argument("--rebind", action="store_true",
                   help="allow a catalog created on another machine to be reused here")
    s.set_defaults(fn=cmd_auto)

    s = sub.add_parser("plan", help="show the move before doing it")
    s.add_argument("--upstream-mbit", type=float, default=0,
                   help="your upload speed, to estimate wall-clock time")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("push", help="pack -> upload -> verify -> reclaim, resumable")
    s.add_argument("--remote", default=DEFAULT_REMOTE)
    s.add_argument("--stage", default=str(HERE / "stage"))
    s.add_argument("--compress", choices=["none", "gz", "bz2", "xz"], default="none",
                   help="none is right for media; gz for documents/source")
    s.add_argument("--daily-cap-gb", type=float, default=DAILY_UPLOAD_BUDGET / GiB)
    s.add_argument("--max-hours", type=float, default=0, help="stop after N hours")
    s.add_argument("--no-verify", dest="verify", action="store_false", default=True)
    s.add_argument("--reclaim", action="store_true",
                   help="trash local files as soon as their remote copy verifies")
    s.add_argument("--keep-stage", action="store_true")
    s.add_argument("--no-wait", action="store_true",
                   help="exit at the daily cap instead of sleeping until it lifts")
    s.add_argument("--transfers", type=int, default=8,
                   help="parallel uploads; 8 suits gigabit, drop to 4 on a slow line")
    s.add_argument("--chunk", default="256M",
                   help="upload chunk size; RAM cost is chunk x transfers")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--expect-host", default=None,
                   help="refuse to run unless the hostname matches. Use this to "
                        "guarantee you are on the PC and not the laptop")
    s.add_argument("--rebind", action="store_true",
                   help="allow a catalog created on another machine to be reused here")
    s.set_defaults(fn=cmd_push)

    s = sub.add_parser("reclaim", help="move already-safe local files to the Recycle Bin")
    s.add_argument("--junk", action="store_true", default=True)
    s.add_argument("--no-junk", dest="junk", action="store_false")
    s.add_argument("--dupes", action="store_true", default=True)
    s.add_argument("--no-dupes", dest="dupes", action="store_false")
    s.add_argument("--archived", action="store_true", default=True)
    s.add_argument("--no-archived", dest="archived", action="store_false")
    s.add_argument("--yes", dest="dry_run", action="store_false", default=True)
    s.add_argument("--expect-host", default=None,
                   help="refuse to run unless the hostname matches. Use this to "
                        "guarantee you are on the PC and not the laptop")
    s.add_argument("--rebind", action="store_true",
                   help="allow a catalog created on another machine to be reused here")
    s.set_defaults(fn=cmd_reclaim)

    s = sub.add_parser("whoami", help="which machine is this, and what drives does it have")
    s.set_defaults(fn=cmd_whoami)

    s = sub.add_parser("status", help="progress dashboard")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("errors", help="list failures")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_errors)

    s = sub.add_parser("doctor", help="preflight checks")
    s.add_argument("--remote", default=DEFAULT_REMOTE)
    s.add_argument("--stage", default=str(HERE / "stage"))
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("find", help="search the catalog")
    s.add_argument("pattern")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("restore", help="pull files back from Drive")
    s.add_argument("pattern")
    s.add_argument("--to", default="./restored")
    s.add_argument("--keep-bundle", action="store_true")
    s.set_defaults(fn=cmd_restore)

    s = sub.add_parser("backup-index", help="upload the catalog itself to Drive")
    s.add_argument("--remote", default=DEFAULT_REMOTE)
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_backup_index)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        say("\ninterrupted - state is saved, re-run the same command to continue")
        return 130


if __name__ == "__main__":
    sys.exit(main())
