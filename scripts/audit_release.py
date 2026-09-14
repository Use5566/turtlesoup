"""Inspect staged paths/content without printing credentials."""
import json
import re
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), *args], cwd=ROOT)

if __name__ == '__main__':
    paths = git('ls-files', '-z').decode().split('\0')
    passwords = []
    local = ROOT / 'private/roster.json'
    if local.exists():
        passwords = [str(x['password']) for x in json.loads(local.read_text(encoding='utf-8-sig'))]
    issues = []
    for name in filter(None, paths):
        if name.startswith(('private/', 'work/', 'dist/')) or name.endswith(('.db', '.sqlite', '.pem')) or (name.startswith('.env') and name != '.env.example'):
            issues.append(name + ': private path')
        content = git('show', ':' + name).decode('utf-8', errors='replace')
        if any(re.search(r'(?<!\d)' + re.escape(p) + r'(?!\d)', content) for p in passwords if p != '12345'):
            issues.append(name + ': actual roster credential')
        if re.search(r'-----BEGIN (?:RSA )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[0-9A-Za-z]{20,}', content):
            issues.append(name + ': secret signature')
    if issues:
        raise SystemExit('\n'.join(issues))
    print('Staged release audit passed; no private paths or real credentials found.')
