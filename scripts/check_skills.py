"""Offline structure and bootstrap checks, with no third-party dependencies."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'.venv', 'venv', '.mastergo', '.browser-profile', 'browser-profile', '.auth',
             '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'design-bundle', 'output'}


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and p.name != '.DS_Store' and '.git' not in p.relative_to(root).parts}


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def main() -> None:
    skills = [ROOT]
    assert skills, 'No skills found'
    for skill in skills:
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        assert text.startswith('---\n')
        frontmatter = text.split('---', 2)[1]
        assert re.search(r'^name:\s*' + re.escape('mastergo-capture') + r'\s*$', frontmatter, re.M)
        assert re.search(r'^description:\s*\S', frontmatter, re.M)
        for path in skill.rglob('*'):
            if '.git' in path.relative_to(skill).parts:
                continue
            assert not path.is_symlink(), f'Unexpected symlink: {path}'
            assert not set(path.relative_to(skill).parts) & FORBIDDEN, path
            if not path.is_file() or path.name == '.DS_Store':
                continue
            assert path.stat().st_size < 1_000_000, f'Unexpected large file: {path}'
            if path.suffix == '.py':
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            assert path.name not in {'Cookies', 'Login Data', 'Local State', '.env', 'mastergo.json'}
            content = path.read_text(encoding='utf-8')
            assert not re.search(r'gh[pousr]_[A-Za-z0-9]{20,}', content), 'Possible GitHub credential'
        before = snapshot(skill)
        with tempfile.TemporaryDirectory(prefix='skills-check-') as temporary:
            base = Path(temporary)
            project = base / 'project with spaces'
            init = str(skill / 'scripts/init_project.py')
            run(init, '--project', str(project), '--role', 'collector', cwd=base)
            mapping = project / 'design-bundle/DESIGN_MAP.md'
            mapping.write_text('User-maintained map', encoding='utf-8')
            run(init, '--project', str(project), cwd=base)
            assert mapping.read_text() == 'User-maintained map'
            launcher = str(project / 'tools/mastergo-capture/run.py')
            paths = json.loads(run(launcher, 'paths', cwd=base))
            assert paths['project'] == str(project.resolve())
            assert paths['output'] == str(project.resolve() / 'design-bundle')
            assert not (project / 'tools/mastergo-capture/.template-only').exists()
            archive = base / 'skill.zip'
            run(str(skill / 'scripts/package_share.py'), '--out', str(archive), cwd=base)
            with ZipFile(archive) as z:
                assert z.testzip() is None
                assert all(not (set(Path(n).parts) & FORBIDDEN) for n in z.namelist())
                assert 'mastergo-capture/templates/tool/.template-only' in z.namelist()
        assert before == snapshot(skill), 'Bootstrap changed the skill template'
    print(f'OK: {len(skills)} skill(s); syntax, clean template, bootstrap and share package verified')


if __name__ == '__main__':
    main()
