"""Project-owned paths. Nothing is resolved against the caller's working directory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4


def project_root(explicit: Path | None = None) -> Path:
    tool = Path(__file__).resolve().parents[2]
    root = explicit.resolve() if explicit else tool.parent.parent
    if not (root / ".mastergo/project.json").is_file():
        raise ValueError(
            "项目尚未初始化；请使用 skill 的 scripts/init_project.py --project 项目目录"
        )
    return root


def within(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("写入路径必须位于当前项目内")
    return resolved


def project_file(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def bundle_path(root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    if path.parts and path.parts[0] == "design-bundle":
        return (root / path).resolve()
    return (root / "design-bundle" / path).resolve()


def configure(args: argparse.Namespace) -> Path:
    root = project_root(args.project_root)
    state = within(root, root / ".mastergo")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(within(root, state / "browsers"))
    config = json.loads((state / "project.json").read_text(encoding="utf-8"))
    if config.get("role") == "consumer" and args.command != "validate":
        raise ValueError(
            "当前项目为 consumer，仅允许读取/校验产物；切换角色请重新初始化并显式指定 --change-role"
        )
    args.profile = (
        within(root, project_file(root, args.profile))
        if args.profile
        else within(root, state / "browser-profile")
    )
    if args.command in {"prepare", "validate"}:
        args.path = bundle_path(root, args.path)
        if args.command == "prepare":
            within(root, args.path)
    if args.command == "auth-export":
        args.out = (
            within(root, project_file(root, args.out))
            if args.out
            else within(root, state / "auth/mastergo.json")
        )
        if args.out.is_relative_to((root / "design-bundle").resolve()):
            raise ValueError("登录态不能写入可分享的 design-bundle 目录")
    if args.command == "capture":
        args.out = within(root, bundle_path(root, args.out or Path("capture-" + uuid4().hex[:12])))
        for name in ("auth_state", "url_file"):
            if getattr(args, name):
                setattr(args, name, project_file(root, getattr(args, name)))
    if getattr(args, "layout_overrides", None):
        args.layout_overrides = project_file(root, args.layout_overrides)
    return root
