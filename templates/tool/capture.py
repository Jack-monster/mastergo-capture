"""Run with uv run python capture.py ... from this project directory."""

import sys
from pathlib import Path

tool_root = Path(__file__).resolve().parent
if (tool_root / ".template-only").exists():
    raise SystemExit("这是 skill 模板，请先使用 scripts/init_project.py 初始化项目")
sys.dont_write_bytecode = True
sys.path.insert(0, str(tool_root / "src"))
from mastergo_capture.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        raise SystemExit(f"错误：{error}") from None
