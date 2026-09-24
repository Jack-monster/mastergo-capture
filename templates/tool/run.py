"""Project launcher; only the Python standard library is needed to start."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def project_paths(tool: Path) -> dict[str, Path]:
    root = tool.resolve().parent.parent
    return {
        "project": root,
        "tool": tool.resolve(),
        "state": root / ".mastergo",
        "venv": root / ".mastergo/venv",
        "browser_profile": root / ".mastergo/browser-profile",
        "browsers": root / ".mastergo/browsers",
        "auth": root / ".mastergo/auth",
        "cache": root / ".mastergo/cache",
        "python": root / ".mastergo/python",
        "tmp": root / ".mastergo/tmp",
        "logs": root / ".mastergo/logs",
        "output": root / "design-bundle",
    }


def environment(paths: dict[str, Path]) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "UV_PROJECT_ENVIRONMENT": str(paths["venv"]),
            "UV_CACHE_DIR": str(paths["cache"] / "uv"),
            "UV_PYTHON_INSTALL_DIR": str(paths["python"]),
            "PLAYWRIGHT_BROWSERS_PATH": str(paths["browsers"]),
            "PYTHONPYCACHEPREFIX": str(paths["cache"] / "pycache"),
            "TMPDIR": str(paths["tmp"]),
            "TMP": str(paths["tmp"]),
            "TEMP": str(paths["tmp"]),
        }
    )
    return env


def execute(arguments: list[str], paths: dict[str, Path], label: str) -> int:
    started = datetime.now(timezone.utc).isoformat()  # noqa: UP017 - bootstrap supports Python 3.9
    code = 1
    try:
        code = subprocess.call(arguments, cwd=paths["project"], env=environment(paths))
    except KeyboardInterrupt:
        code = 130
    finally:
        record = {
            "command": label,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            "exit_code": code,
        }
        # No CLI arguments, URLs, cookies or raw browser exceptions in run metadata.
        path = paths["logs"] / (uuid4().hex + ".json")
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    tool = Path(__file__).resolve().parent
    if (tool / ".template-only").exists():
        raise ValueError("这是 skill 模板，不能在此运行；请先用 scripts/init_project.py 初始化项目")
    paths = project_paths(tool)
    if any(not path.resolve().is_relative_to(paths["project"]) for path in paths.values()):
        raise ValueError("运行路径通过符号链接指向项目外")
    config_path = paths["state"] / "project.json"
    if not config_path.is_file():
        raise ValueError("项目尚未初始化；请先用 skill 的 scripts/init_project.py 初始化项目")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    command = args[0] if args else "--help"
    if command == "paths":
        print(
            json.dumps(
                {key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2
            )
        )
        return 0
    if config.get("role") == "consumer" and command not in {"validate", "paths", "--help", "-h"}:
        raise ValueError("当前项目为 consumer；仅允许读取/校验产物")
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("未找到 uv，请安装 uv 后重试")
    for key in ("state", "auth", "cache", "python", "tmp", "logs", "output"):
        paths[key].mkdir(parents=True, exist_ok=True)
    if command == "setup":
        if args[1:] not in ([], ["--with-browser"], ["--with-browser", "--with-deps"]):
            raise ValueError("用法：run.py setup [--with-browser [--with-deps]]")
        code = execute([uv, "sync", "--locked", "--no-dev", "--project", str(tool)], paths, "setup")
        if code or "--with-browser" not in args:
            return code
        args = ["install-browser"] + (["--with-deps"] if "--with-deps" in args else [])
        command = "install-browser"
    base = [uv, "run", "--locked", "--no-dev", "--project", str(tool)]
    if command == "install-browser":
        if args[1:] not in ([], ["--with-deps"]):
            raise ValueError("用法：run.py install-browser [--with-deps]")
        return execute(base + ["playwright", "install", "chromium"] + args[1:], paths, command)
    return execute(
        base + ["python", str(tool / "capture.py"), "--project-root", str(paths["project"])] + args,
        paths,
        command if not command.startswith("-") else "cli",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        raise SystemExit(f"错误：{error}") from None
