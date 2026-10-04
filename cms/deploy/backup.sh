#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/arcadian-content
exec 9>/run/lock/arcadian-content-backup.lock
flock -n 9 || exit 0
# One uncompressed archive and its encrypted counterpart must both fit.
media_bytes=$(du -sb media | cut -f1)
free_bytes=$(df -B1 --output=avail backups | tail -n 1 | tr -d ' ')
if (( free_bytes < 2 * media_bytes + 1073741824 )); then
  echo 'Insufficient free disk space for a consistent encrypted backup.' >&2
  exit 1
fi
docker compose --profile operator run --rm --no-deps backup > backups/.result.json
python3 /opt/arcadian-content/finish-backup.py backups/.result.json
rm -f backups/.result.json
