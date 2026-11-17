# SQLite migration

Personal Media Hub keeps `data/jobs.json` for compatibility while using
`data/media_hub.sqlite3` as the primary job database.

On the first start, the application:

1. Copies `jobs.json` to `jobs.json.pre-sqlite.bak` without overwriting an
   existing backup.
2. Imports jobs with their original IDs, paths and timestamps in one SQLite
   transaction.
3. Uses upserts, so restarting the migration does not duplicate jobs or files.
4. Verifies that SQLite contains at least every unique job from `jobs.json`.

The application continues to mirror updates to `jobs.json`. Do not delete the
JSON file or its backup until the installed runtime has been verified.

## Rollback

1. Stop Personal Media Hub.
2. Copy `jobs.json.pre-sqlite.bak` back to `jobs.json` only if the current JSON
   file is unavailable or invalid. Preserve a copy of both files first.
3. Move `media_hub.sqlite3` and its `-wal`/`-shm` companions to a quarantine
   directory; do not delete them.
4. Run the previous verified release and compare job/file counts before
   restoring service.
