#!/usr/bin/env python3
"""Checks this repo for material that must not be published. Scans the working tree and every blob in git history.

Usage:
  python tools/scan_public.py [--terms extra-terms.txt] [--game-archive <unmodded assets.zip>] [--commit-email <address>]

--terms         a file outside the repo with one extra private word per line, such as your name or email.
--game-archive  also reports any line of 40 or more characters that also appears in the game's scripts.
--commit-email  the one address commits may use. Without it, commit emails are listed and not judged.
"""
import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = 'tools/scan_public.py'
PATTERNS = {
    'personal path': re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+|/home/[a-z0-9_-]+/|/Users/[A-Za-z0-9._-]+/'),
    'email': re.compile(r'[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|anthropic\.com)[A-Za-z0-9-]+\.[A-Za-z]{2,}'),
    'token': re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY'),
    'save id': re.compile(r'game-\d{6,}-\d+'),
}
BLOCKED_NAME = re.compile(r'(^|/)(assets[^/]*\.zip|[^/]*\.sav|lab\.toml|settings(\.old)?\.json|log\.txt|error_log\.json)$', re.I)
BLOCKED_SUFFIX = {'.png', '.jpg', '.jpeg', '.ogg', '.wav', '.fsb', '.bank', '.dll', '.exe', '.zip', '.rar', '.7z', '.sav', '.ttf', '.otf'}
ALLOWED_GML = 'examples/'
MAX_BYTES = 512 * 1024


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout


def versions():
    """Every path and blob that any commit has held, plus files not yet committed."""
    seen = set()
    has_commits = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', 'HEAD'], capture_output=True).returncode == 0
    for commit in (git('rev-list', '--all').decode().split() if has_commits else []):
        for line in git('ls-tree', '-r', commit).decode('utf-8', 'replace').splitlines():
            meta, path = line.split('\t', 1)
            blob = meta.split()[2]
            if (blob, path) not in seen:
                seen.add((blob, path))
                yield f'history:{commit[:8]}', path, git('cat-file', 'blob', blob)
    for path in git('ls-files', '--cached', '--others', '--exclude-standard').decode('utf-8', 'replace').splitlines():
        full = ROOT / path
        if full.is_file():
            yield 'tree', path, full.read_bytes()


def game_lines(archive):
    lines = set()
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if name.endswith('.gml') and '/mmapi/' not in name:
                for line in z.read(name).decode('utf-8', 'replace').splitlines():
                    line = line.strip()
                    if len(line) >= 40:
                        lines.add(line)
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--terms', type=Path)
    ap.add_argument('--game-archive', type=Path)
    ap.add_argument('--commit-email')
    args = ap.parse_args()
    terms = [t.strip() for t in args.terms.read_text(encoding='utf-8').splitlines() if t.strip()] if args.terms else []
    native = game_lines(args.game_archive) if args.game_archive else set()
    findings = set()
    files = 0
    for where, path, data in versions():
        files += 1
        if BLOCKED_NAME.search(path):
            findings.add((where, path, 'blocked file name'))
        if Path(path).suffix.lower() in BLOCKED_SUFFIX:
            findings.add((where, path, 'blocked file type'))
        if path.endswith('.gml') and not path.startswith(ALLOWED_GML):
            findings.add((where, path, 'game script outside examples'))
        if len(data) > MAX_BYTES:
            findings.add((where, path, f'large file: {len(data)} bytes'))
        text = data.decode('utf-8', 'replace')
        if path != SELF:
            for label, pattern in PATTERNS.items():
                for m in pattern.finditer(text):
                    findings.add((where, path, f'{label}: {m.group(0)[:60]}'))
        lowered = text.lower()
        for term in terms:
            if term.lower() in lowered:
                findings.add((where, path, 'private term from --terms file'))
        for line in text.splitlines():
            if line.strip() in native:
                findings.add((where, path, f'matches game script: {line.strip()[:60]}'))
    commits = 0
    emails = set()
    if subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', 'HEAD'], capture_output=True).returncode == 0:
        log = git('log', '--all', '--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x01').decode('utf-8', 'replace')
        for record in filter(str.strip, log.split('\x01')):
            commits += 1
            parts = record.strip().split('\x00')
            emails.update((parts[2], parts[4]))
            if args.commit_email:
                for email in (parts[2], parts[4]):
                    if email != args.commit_email:
                        findings.add(('commit', parts[0][:8], f'unexpected commit email: {email}'))
            for label, pattern in PATTERNS.items():
                for m in pattern.finditer(parts[5]):
                    findings.add(('commit', parts[0][:8], f'{label} in message: {m.group(0)[:60]}'))
            for term in terms:
                if term.lower() in parts[5].lower():
                    findings.add(('commit', parts[0][:8], 'private term in message'))
    print(f'scanned {files} file versions and {commits} commits; extra terms: {len(terms)}; game lines compared: {len(native)}')
    print('commit emails:', sorted(emails))
    for row in sorted(findings):
        print(' | '.join(row))
    print(f'{len(findings)} finding(s)')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
