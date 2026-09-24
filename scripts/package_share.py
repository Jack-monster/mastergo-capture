"""Package the read-only skill template, excluding every project/runtime artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def package(root: Path, destination: Path) -> None:
    root, destination = root.resolve(), destination.resolve()
    if destination.is_relative_to(root):
        raise ValueError("分享包必须写入项目目录，不能写入 skill")
    files = [root / "SKILL.md"]
    for folder, pattern in [("scripts", "*.py"), ("references", "*.md"), ("agents", "*.yaml")]:
        files.extend(sorted((root / folder).glob(pattern)))
    template = root / "templates/tool"
    top = {
        "capture.py",
        "run.py",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        ".python-version",
        ".gitignore",
        ".template-only",
    }
    files.extend(template / name for name in sorted(top) if (template / name).is_file())
    files.extend(sorted((template / "src/mastergo_capture").glob("*.py")))
    files.extend(sorted((template / "references").glob("*.md")))
    required = [
        "SKILL.md",
        "scripts/init_project.py",
        "templates/tool/run.py",
        "templates/tool/src/mastergo_capture/paths.py",
        "templates/tool/uv.lock",
        "templates/tool/.template-only",
    ]
    names = {p.relative_to(root).as_posix() for p in files}
    if not set(required).issubset(names):
        raise ValueError("模板缺少必要文件")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.zip")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("模板不允许外部路径或符号链接")
                archive.write(path, "mastergo-capture/" + path.relative_to(root).as_posix())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"{destination} ({destination.stat().st_size:,} bytes; {len(files)} files)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        package(Path(__file__).resolve().parents[1], args.out)
    except (ValueError, OSError) as error:
        raise SystemExit(f"错误：{error}") from None
