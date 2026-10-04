#!/usr/bin/env python3
"""Forced SSH command: exports only the last verified encrypted backup."""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path('/opt/arcadian-content/backups')
with open('/run/lock/arcadian-content-backup.lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_SH)
    record = json.loads((root / 'latest.json').read_text())
    if not re.fullmatch(r'arcadian-\d{8}T\d{12}Z\.zip\.age', record['archive']):
        raise SystemExit('Unexpected archive name.')
    with (root / record['archive']).open('rb') as file:
        if hashlib.file_digest(file, 'sha256').hexdigest() != record['sha256']:
            raise SystemExit('Encrypted archive checksum mismatch.')
        file.seek(0)
        header = json.dumps(record).encode()
        sys.stdout.buffer.write(struct.pack('!I', len(header)) + header)
        sys.stdout.buffer.flush()
        request = sys.stdin.buffer.read(1)
        if request == b'1':
            while chunk := file.read(1024 * 1024):
                sys.stdout.buffer.write(chunk)
        elif request != b'0':
            raise SystemExit('Unsupported backup transfer request.')
