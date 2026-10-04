#!/usr/bin/env python3
"""Copy a verified encrypted archive over pinned, restricted SSH to the owner's Mac."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone

configuration = json.loads(Path(sys.argv[1]).read_text())
root = Path(configuration['destination'])
root.mkdir(parents=True, exist_ok=True, mode=0o700)


def file_sha256(file):
    """Use the system Python on macOS, including its bundled Python 3.9."""
    digest = hashlib.sha256()
    while chunk := file.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


with (root / '.pull.lock').open('a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(0)
    command = ['/usr/bin/ssh', '-T', '-i', configuration['identity'],
               '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
               '-o', 'ServerAliveCountMax=2', '-o', 'UserKnownHostsFile=' + configuration['known_hosts'],
               'root@' + configuration['host']]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    temporary = None
    try:
        def read_exact(length):
            value = bytearray()
            while len(value) < length:
                chunk = process.stdout.read(min(length - len(value), 1024 * 1024))
                if not chunk:
                    raise RuntimeError('Incomplete encrypted backup transfer.')
                value.extend(chunk)
            return bytes(value)
        header_size = struct.unpack('!I', read_exact(4))[0]
        if header_size > 8192:
            raise RuntimeError('Unexpected backup metadata size.')
        record = json.loads(read_exact(header_size))
        name = record['archive']
        if not re.fullmatch(r'arcadian-\d{8}T\d{12}Z\.zip\.age', name):
            raise RuntimeError('Unexpected backup filename.')
        if not isinstance(record['bytes'], int) or record['bytes'] <= 0 or not re.fullmatch(r'[0-9a-f]{64}', record['sha256']):
            raise RuntimeError('Invalid backup size or checksum.')
        target = root / name
        already_verified = target.exists() and target.stat().st_size == record['bytes']
        if already_verified:
            with target.open('rb') as file:
                already_verified = file_sha256(file) == record['sha256']
        if not already_verified and shutil.disk_usage(root).free < record['bytes'] + 1024**3:
            raise RuntimeError('The Mac needs at least 1 GiB free after the backup transfer.')
        process.stdin.write(b'0' if already_verified else b'1')
        process.stdin.flush()
        process.stdin.close()
        digest = hashlib.sha256()
        remaining = 0 if already_verified else record['bytes']
        if not already_verified:
            temporary = root / (name + '.part')
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            destination = os.fdopen(descriptor, 'wb')
        else:
            destination = None
        try:
            while remaining:
                chunk = read_exact(min(remaining, 1024 * 1024))
                digest.update(chunk)
                if destination:
                    destination.write(chunk)
                remaining -= len(chunk)
        finally:
            if destination:
                destination.close()
        if process.stdout.read(1) or process.wait(timeout=10) != 0 or (not already_verified and digest.hexdigest() != record['sha256']):
            raise RuntimeError('Encrypted archive transfer verification failed.')
        if temporary:
            os.replace(temporary, target)
            temporary = None
        record['offsite_verified'] = True
        record['offsite_checked_at'] = datetime.now(timezone.utc).isoformat()
        latest = root / '.latest.json.part'
        latest.write_text(json.dumps(record))
        latest.chmod(0o600)
        os.replace(latest, root / 'latest.json')
        # Retain up to 14 captures, bounded to 2 GiB. Preserve the latest archive.
        kept_bytes = 0
        for index, old in enumerate(sorted(root.glob('arcadian-*.zip.age'), reverse=True)):
            kept_bytes += old.stat().st_size
            if index > 0 and (index >= 14 or kept_bytes > 2 * 1024**3):
                old.unlink()
        print(json.dumps(record))
    finally:
        if process.poll() is None:
            process.terminate()
        if temporary:
            temporary.unlink(missing_ok=True)
