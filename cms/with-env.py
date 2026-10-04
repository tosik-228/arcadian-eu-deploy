#!/usr/bin/env python3
import os
import sys
from pathlib import Path
if len(sys.argv) < 3:
    raise SystemExit('Usage: with-env.py PRIVATE_ENV COMMAND [ARGS]')
env = dict(os.environ)
for line in Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        name, value = line.split('=', 1)
        env[name] = value.replace('\\n', '\n')
os.execvpe(sys.argv[2], sys.argv[2:], env)
