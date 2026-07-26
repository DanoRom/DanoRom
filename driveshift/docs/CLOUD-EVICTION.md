# Getting rid of OneDrive, iCloud and Dropbox

You want them gone. Fine — but do it in this order, because there are two ways
to lose files permanently here and both of them look like nothing went wrong.

## Trap 1: online-only placeholders

OneDrive "Files On-Demand", iCloud "Optimise Mac Storage", and Dropbox "Smart
Sync" all leave files that **look** normal in Explorer but are 0 bytes on disk.
The real content lives only in the cloud. Archive one of those and you archive an
empty stub. You will not notice until you go looking for the file a year later.

Check for it before anything else:

```powershell
# Windows — files present in the listing but 0 bytes on disk
Get-ChildItem "$env:USERPROFILE\OneDrive" -Recurse -File |
  Where-Object { $_.Length -eq 0 -or $_.Attributes -match 'Offline' } |
  Measure-Object | Select-Object Count
```

Force a full download first:

- **OneDrive** — right-click the OneDrive folder → *Always keep on this device*.
  Then wait for the sync icon to go solid green. Or turn Files On-Demand off
  entirely in Settings → Sync and backup → Advanced.
- **iCloud Drive** — System Settings → Apple ID → iCloud Drive → turn **off**
  *Optimise Mac Storage*, then wait. On Windows, iCloud for Windows → check
  *Keep downloaded*.
- **Dropbox** — right-click the folder → *Smart Sync* → *Local*.

This can take hours and pull a lot of data. Let it finish. Re-run the check above
until the count is zero.

## Trap 2: a local delete propagates upstream

While the sync client is running and linked, deleting a file locally deletes it
from the cloud. If your only copy of something is in there, and you have not yet
archived it to Black Mamba, it is gone from both places at once.

That is why `rules.json` tiers these folders as **ARCHIVE, not JUNK**: they get
copied to Drive and MD5-verified *before* anything local is removed.

---

## The order

1. **Force full download** (above). Verify no 0-byte placeholders remain.
2. **Pause syncing** — don't unlink yet, just pause. OneDrive: *Pause syncing →
   24 hours*. Dropbox: *Pause syncing*. iCloud: leave it, step 5 handles it.
3. **Archive them.** `dr push` copies the contents into Black Mamba and verifies
   each MD5 against Google.
4. **Confirm.** `dr status` — uploaded equals verified, errors zero. Spot-check by
   opening a couple of restored files, not just hashing them.
5. **Unlink the account** *before* deleting anything locally:
   - OneDrive: Settings → Account → **Unlink this PC**
   - Dropbox: Preferences → Account → **Unlink this Dropbox**
   - iCloud: sign out of iCloud Drive, choosing **Keep a copy** if offered
   Unlinking leaves the local folder on disk but stops it being a sync source.
   Now a local delete is only a local delete.
6. **Reclaim.** `dr reclaim --yes` moves the now-redundant local folders to the
   Recycle Bin.
7. **Uninstall the clients.** Add/Remove Programs. On Windows, OneDrive also has
   a Group Policy / registry switch to stop it reinstalling itself:
   ```
   reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\OneDrive" ^
     /v DisableFileSyncNGSC /t REG_DWORD /d 1 /f
   ```
8. **Optional — delete the cloud-side data.** Only after 1-6, and only via each
   service's website. Note OneDrive keeps deleted files in its recycle bin for 30
   days and iCloud for 30 days, so you have a grace period either way.

## If you skipped straight to deleting

If you already deleted a synced folder and the client was linked and running:

- **OneDrive** — onedrive.live.com → Recycle bin. 30 days.
- **Dropbox** — dropbox.com → Deleted files. 30 days on free, 180 on paid.
- **iCloud Drive** — icloud.com → Drive → Recently Deleted. 30 days.

Restore there first, then start over at step 1.
