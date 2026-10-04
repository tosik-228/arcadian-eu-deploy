#!/usr/bin/env python3
import os
from pathlib import Path
root = Path(__file__).resolve().parent
env = dict(os.environ)
for line in (root / '.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        env.setdefault(key, value)
if env.get('DJANGO_ENV') != 'local':
    raise SystemExit('This runner is local only.')
env['DB_USER'] = env['RUNTIME_DB_USER']
env['DB_PASSWORD'] = env['RUNTIME_DB_PASSWORD']
env['GUNICORN_CONTROL_SOCKET'] = str(root / '.state/gunicorn.sock')
os.chdir(root)
os.execve(str(root / '.venv/bin/gunicorn'), [str(root / '.venv/bin/gunicorn'), 'config.wsgi:application', '--config', 'gunicorn.conf.py', '--bind', '127.0.0.1:' + env.get('CMS_PORT', '8057')], env)
