"""Validate documentation migration from the repository root; standard library only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from localize_docs import FENCE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command_body(block):
    lines = block.splitlines()[1:-1]
    return '\n'.join(line for line in lines if line.strip() and not line.lstrip().startswith('#'))


def main():
    manifest = json.loads(Path('docs/localization-manifest.json').read_text(encoding='utf-8'))
    issues = []
    checked = 0
    for entry in manifest['documents']:
        original = Path(entry['zh_cn']).read_bytes()
        if sha(original) != entry['original_sha256']:
            issues.append(entry['zh_cn'] + ': original snapshot changed')
        original_text = original.decode('utf-8-sig').replace('\r\n', '\n')
        original_blocks = [m[0] for m in FENCE.finditer(original_text)]
        original_tables = sum(line.startswith('|') for line in original_text.splitlines())
        for language in ('english', 'zh_cn', 'zh_hk'):
            file = Path(entry[language])
            if not file.is_file():
                issues.append(str(file) + ': missing')
                continue
            checked += 1
            text = file.read_text(encoding='utf-8-sig')
            translated_blocks = [m[0] for m in FENCE.finditer(text)]
            if len(translated_blocks) != len(original_blocks):
                issues.append(str(file) + ': fenced block count changed')
            if sum(line.startswith('|') for line in text.splitlines()) != original_tables:
                issues.append(str(file) + ': table row count changed')
            for old, new in zip(original_blocks, translated_blocks):
                if old.splitlines()[0].strip() in ('```python', '```powershell', '```bash', '```json'):
                    if command_body(old) != command_body(new):
                        issues.append(str(file) + ': executable command / JSON example changed')
            prose = FENCE.sub('', text)
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', prose):
                if '://' in target or target.startswith('#'):
                    continue
                target = target.split('#', 1)[0]
                if not (file.parent / target).exists():
                    issues.append(str(file) + ': missing link ' + target)
    for name in manifest['excluded_historical_documents']:
        original = subprocess.check_output(['git', 'show', manifest['source_commit'] + ':' + name])
        expected = manifest.get('historical_sha256', {}).get(name, sha(original))
        if sha(Path(name).read_bytes()) != expected:
            issues.append(name + ': excluded historical record changed')
    if issues:
        print('\n'.join(issues))
        return 1
    print(f'PASS: {checked} language files; original snapshot hashes, tables, command/JSON examples and local links')
    print(f'PASS: {len(manifest["excluded_historical_documents"])} historical document baselines verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
