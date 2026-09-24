"""Initialize a project from this skill's read-only template (standard library only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize(
    skill: Path,
    project: Path,
    role: str | None = None,
    update: bool = False,
    change_role: bool = False,
) -> dict[str, str]:
    skill, project = skill.resolve(), project.resolve()
    if project.is_relative_to(skill) or skill.is_relative_to(project):
        raise ValueError("目标必须是独立项目目录，不能使用 skill 目录或其祖先/子目录")
    template = skill / "templates/tool"
    if not template.is_dir():
        raise ValueError("缺少 templates/tool，请使用完整 skill 分享包")
    state = project / ".mastergo"
    tool = project / "tools/mastergo-capture"
    output = project / "design-bundle"
    for path in (state, tool, output):
        if not path.resolve().is_relative_to(project):
            raise ValueError("项目目录中的符号链接指向外部，停止初始化")
    config_path = state / "project.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    old_role = config.get("role")
    role = role or old_role
    if role not in {"collector", "consumer"}:
        raise ValueError("首次初始化需要 --role collector 或 --role consumer")
    if old_role and role != old_role and not change_role:
        raise ValueError("已有项目角色不同；明确切换时添加 --change-role")
    managed = config.get("template_files", {})
    top = {
        "capture.py",
        "run.py",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        ".python-version",
        ".gitignore",
    }
    sources = [template / name for name in sorted(top) if (template / name).is_file()]
    sources.extend(sorted((template / "src/mastergo_capture").glob("*.py")))
    sources.extend(sorted((template / "references").glob("*.md")))
    required = {
        "capture.py",
        "run.py",
        "pyproject.toml",
        "uv.lock",
        "src/mastergo_capture/paths.py",
        "references/layout-consumption.md",
    }
    if not required.issubset({p.relative_to(template).as_posix() for p in sources}):
        raise ValueError("工具模板不完整")
    for target in (config_path, state / "ROLE.md", state / ".gitignore", output / "DESIGN_MAP.md"):
        if not target.resolve().is_relative_to(project):
            raise ValueError("项目配置或地图通过符号链接指向项目外")
    conflicts = []
    for source in sources:
        if source.is_symlink():
            raise ValueError("模板不允许符号链接")
        relative = source.relative_to(template).as_posix()
        target = tool / relative
        if not target.resolve().is_relative_to(project):
            raise ValueError("目标文件通过符号链接指向项目外")
        if (
            target.exists()
            and digest(target) != digest(source)
            and (not update or managed.get(relative) != digest(target))
        ):
            conflicts.append(relative)
    if conflicts:
        raise ValueError("保留已有文件，未执行初始化；冲突：" + ", ".join(conflicts))
    # All conflicts are checked before any project mutation.
    for source in sources:
        target = tool / source.relative_to(template)
        if target.exists() and digest(target) == digest(source):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for path in (state, output, state / "auth", state / "logs", state / "tmp", state / "cache"):
        path.mkdir(parents=True, exist_ok=True)
    new_config = {
        "schema_version": 1,
        "role": role,
        "paths": {
            "tool": "tools/mastergo-capture",
            "runtime": ".mastergo",
            "output": "design-bundle",
        },
        "template_files": {p.relative_to(template).as_posix(): digest(p) for p in sources},
    }
    config_path.write_text(json.dumps(new_config, ensure_ascii=False, indent=2), encoding="utf-8")
    (state / "ROLE.md").write_text(
        f"# 项目角色\n\nrole: {role}\n\n以同目录 project.json 为程序配置。\n", encoding="utf-8"
    )
    ignore = state / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n!.gitignore\n!project.json\n!ROLE.md\n", encoding="utf-8")
    map_path = output / "DESIGN_MAP.md"
    if not map_path.exists():
        map_path.write_text(
            """# 设计资料地图

状态：尚未整理。本文件是索引入口，不代表已采集设计数据。

先进行全局枚举，产物建议命名 all-canvases；再按页面/画板节点 ID 深度采集。
根据实际采集结果按业务模块整理链接、节点 ID、采集范围与缺失项，不猜测模块含义。

消费顺序：本地图 → 画板目录/AGENT_README.md → manifest.json → layout.json 和 LAYOUT_GUIDE.md
→ 图片及原始证据。
""",
            encoding="utf-8",
        )
    return {
        "project": str(project),
        "tool": str(tool),
        "runtime": str(state),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--role", choices=["collector", "consumer"])
    parser.add_argument("--update", action="store_true", help="更新模板管理且未被本地修改的文件")
    parser.add_argument("--change-role", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            initialize(
                Path(__file__).resolve().parents[1],
                args.project,
                args.role,
                args.update,
                args.change_role,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"错误：{error}") from None
