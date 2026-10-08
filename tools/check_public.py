#!/usr/bin/env python3
"""Limited pre-publish scanner. Human review of staged content remains necessary."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TOP = {'README.md', 'AGENTS.md', '.gitignore', '.agents', 'docs', 'templates', 'tools', 'tests'}
PATTERNS = {
    'machine home path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'credential-like token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})\b'),
    'phone-like number': re.compile(r'(?<![\w-])\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\w-])'),
    'email address': re.compile(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
}


def findings(path, body):
    results = []
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(body):
            if label == 'email address' and match.group().endswith('.invalid'):
                continue
            results.append(str(path) + ': ' + label)
            break
    return results


def scan(root=ROOT):
    errors = []
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(p in {'.git', '__pycache__'} for p in rel.parts):
            continue
        if rel.parts[0] == 'private':
            continue
        if path.is_symlink():
            errors.append(str(rel) + ': symbolic links require review')
            continue
        if not path.is_file():
            continue
        if rel.parts[0] not in PUBLIC_TOP:
            errors.append(str(rel) + ': outside public allowlist')
            continue
        try:
            body = path.read_text(encoding='utf-8')
        except (UnicodeError, OSError):
            errors.append(str(rel) + ': non-text/unreadable file requires review')
            continue
        errors.extend(findings(rel, body))
    if (root / '.git').exists():
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True).stdout.decode().split('\0')
        for name in tracked:
            if name.startswith('private/') or (name and name.split('/')[0] not in PUBLIC_TOP):
                errors.append(name + ': non-public file tracked by Git')
    return errors


if __name__ == '__main__':
    problems = scan()
    for problem in problems:
        print(problem)
    print('Limited public scan: ' + ('FAIL' if problems else 'PASS') + '. Review every staged file before publishing.')
    raise SystemExit(bool(problems))
