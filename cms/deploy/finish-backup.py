#!/usr/bin/env python3
"""Publish a checked backup, then retain the two latest successful archives."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

root = Path('/opt/arcadian-content/backups')
result = json.loads(Path(sys.argv[1]).read_text().splitlines()[-1])
name = Path(result['archive']).name
if not re.fullmatch(r'arcadian-\d{8}T\d{12}Z\.zip\.age', name):
    raise SystemExit('Unexpected archive name.')
archive = root / name
if not archive.is_file() or archive.stat().st_size == 0:
    raise SystemExit('Backup archive is missing or empty.')
with archive.open('rb') as file:
    digest = hashlib.file_digest(file, 'sha256').hexdigest()
record = {'archive': name, 'sha256': digest, 'bytes': archive.stat().st_size,
          'files': result['files'], 'completed_at': datetime.now(timezone.utc).isoformat()}
temporary = root / '.latest.json.part'
temporary.write_text(json.dumps(record))
temporary.chmod(0o600)
os.replace(temporary, root / 'latest.json')
for old in sorted(root.glob('arcadian-*.zip.age'), reverse=True)[2:]:
    old.unlink()
print(json.dumps(record))
