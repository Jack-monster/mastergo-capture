"""Command-line entry point; no AI or Computer Use dependency at runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import sync_playwright

from .auth import capture_context, export_auth, validate_auth
from .browser import AdapterError, MasterGoViewer, hierarchy
from .bundle import Bundle, prepare_bundle, validate_url, verify, write_json
from .layout import MODES, read_overrides
from .paths import configure


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MasterGo 查看模式采集器")
    p.add_argument("--project-root", type=Path, help="项目根目录；通常由 run.py 传入")
    p.add_argument("--profile", type=Path, help="项目内浏览器目录，默认 .mastergo/browser-profile")
    p.add_argument("--channel", choices=["chrome", "chromium", "msedge"], default="chromium")
    sub = p.add_subparsers(dest="command", required=True)
    login = sub.add_parser("login", help="在专用浏览器中自行登录")
    login.add_argument("--url", default="https://mastergo.com")
    auth = sub.add_parser("auth-export", help="导出仅含 MasterGo 登录状态的轻量 JSON")
    auth.add_argument("--out", type=Path, help="默认写入项目 .mastergo/auth/mastergo.json")
    capture = sub.add_parser("capture", help="从链接采集结构、属性和图片")
    source = capture.add_mutually_exclusive_group()
    source.add_argument("--url", help="MasterGo 设计链接；含访问令牌时建议使用 --url-file")
    source.add_argument("--url-file", type=Path)
    capture.add_argument(
        "--out", type=Path, help="产物名称或项目内绝对路径；相对路径以 design-bundle 为基准"
    )
    capture.add_argument("--scope", choices=["layer", "page", "file"], default="file")
    capture.add_argument("--max-nodes", type=int, default=5000)
    capture.add_argument("--max-tree-seconds", type=int, default=1800)
    capture.add_argument(
        "--export", choices=["all", "roots-and-leaves", "roots", "none"], default="roots-and-leaves"
    )
    capture.add_argument("--headless", action="store_true")
    capture.add_argument("--auth-state", type=Path, help="加载登录态 JSON；不使用本地 profile")
    capture.add_argument("--settle-ms", type=int, default=180)
    capture.add_argument("--export-wait-ms", type=int, default=5000)
    capture.add_argument("--download-timeout-ms", type=int, default=30000)
    capture.add_argument(
        "--flat",
        action="store_true",
        help="只滚动读取图层树，不自动展开折叠节点；用于枚举所有画板而不进入组件内部",
    )
    capture.add_argument("--coordinate-mode", choices=MODES, default="unknown")
    capture.add_argument("--layout-overrides", type=Path)
    prepare = sub.add_parser("prepare", help="离线生成布局 JSON、HTML 骨架及消费指南")
    prepare.add_argument("path", type=Path)
    prepare.add_argument("--coordinate-mode", choices=MODES, default="unknown")
    prepare.add_argument("--layout-overrides", type=Path)
    check = sub.add_parser("validate", help="校验资料包结构、引用和文件哈希")
    check.add_argument("path", type=Path)
    return p


def crawl(args: argparse.Namespace, url: str, bundle: Bundle) -> int:
    with capture_context(args.profile, args.channel, args.headless, args.auth_state) as context:
        try:
            page = context.pages[0] if context.pages else context.new_page()
            viewer = MasterGoViewer(
                page, args.settle_ms, args.export_wait_ms, args.download_timeout_ms
            )
            print("打开设计稿，等待图层树……", flush=True)
            viewer.open(url)
            query = parse_qs(urlsplit(page.url).query)
            input_query = parse_qs(urlsplit(url).query)
            root_id = (
                query.get("source_layer_id")
                or query.get("layer_id")
                or input_query.get("source_layer_id")
                or input_query.get("layer_id")
                or [""]
            )[0]
            if args.scope == "layer" and not root_id:
                raise AdapterError(
                    "链接未指定 layer_id；选中图层后复制链接，或使用 --scope page/file"
                )
            pages: list[dict[str, Any]] = (
                viewer.pages()
                if args.scope == "file"
                else [
                    {
                        "index": None,
                        "name": (
                            page.locator(".layer_content_page .highlight")
                            .first.inner_text()
                            .strip()
                            if page.locator(".layer_content_page .highlight").count()
                            else "链接所在页面"
                        ),
                    }
                ]
            )
            for page_info in pages:
                if len(bundle.nodes) >= args.max_nodes:
                    bundle.error("tree", None, "达到 max-nodes 上限，剩余页面未采集")
                    break
                page_id = (
                    viewer.select_page(page_info["index"])
                    if page_info["index"] is not None
                    else query.get("page_id", ["unknown"])[0]
                )
                if any(existing["id"] == page_id for existing in bundle.pages):
                    raise AdapterError("页面切换得到重复 ID，停止采集以避免错误关联")
                print(f"扫描页面：{page_info['name']}", flush=True)
                rows, complete = viewer.scan_tree(
                    args.max_nodes - len(bundle.nodes),
                    root_id if args.scope == "layer" else None,
                    args.max_tree_seconds,
                    expand_collapsed=not args.flat,
                )
                page_nodes = hierarchy(rows, page_id)
                bundle.nodes.extend(page_nodes)
                bundle.pages.append(
                    {
                        "id": page_id,
                        "name": page_info["name"],
                        "node_ids": [n["id"] for n in page_nodes],
                        "root_ids": [n["id"] for n in page_nodes if n["parent_id"] is None],
                        "tree_complete": complete,
                    }
                )
                if not complete:
                    bundle.error("tree", root_id, "图层枚举达到数量或时间限制")
                positions = {r["id"]: r["y"] for r in rows}
                exports: list[dict[str, Any]] = []
                for index, node in enumerate(page_nodes):
                    print(f"[{index + 1}/{len(page_nodes)}] {node['name']}", flush=True)
                    try:
                        viewer.select_node(node["id"], positions[node["id"]])
                        design = viewer.inspector()
                        node["evidence_path"] = bundle.evidence(node["id"], design)
                        node["design"] = {
                            "css": design["css"],
                            "text": design["text_content"],
                            "bounds": design["bounds"],
                            "css_properties": design["css_properties"],
                            "coordinate_space": design["coordinate_space"],
                            "properties": [r for s in design["sections"] for r in s["rows"]],
                        }
                        node["capture_status"] = "properties_captured"
                        is_root = node["parent_id"] is None
                        is_leaf_art = (
                            not node["has_children_in_ui"]
                            and "font-size" not in design["css_properties"]
                        )
                        should_export = (
                            args.export == "all"
                            or (args.export in {"roots", "roots-and-leaves"} and is_root)
                            or (args.export == "roots-and-leaves" and is_leaf_art)
                        )
                        if should_export:
                            exports.append(node)
                    except (BrowserError, AdapterError, ValueError, OSError) as error:
                        # Browser exceptions may contain signed URLs; never serialize them.
                        message = (
                            str(error) if isinstance(error, AdapterError) else type(error).__name__
                        )
                        bundle.error("node", node["id"], message)
                        node["capture_status"] = "partial"
                        if page.is_closed():
                            raise AdapterError("浏览器已关闭，已保留当前结果；请重新运行") from None
                    if (index + 1) % 10 == 0:
                        bundle.finish("partial")
                bundle.finish("partial")
                for index, node in enumerate(exports):
                    print(f"导出 [{index + 1}/{len(exports)}] {node['name']}", flush=True)
                    try:
                        viewer.select_node(node["id"], positions[node["id"]])
                        data, name, settings = viewer.export_png()
                        node["asset_ids"] = bundle.asset(node["id"], data, name)
                        node["export_settings"] = settings
                        node["capture_status"] = "captured"
                    except (BrowserError, AdapterError, ValueError, OSError) as error:
                        message = (
                            str(error) if isinstance(error, AdapterError) else type(error).__name__
                        )
                        bundle.error("export", node["id"], message)
                        node["capture_status"] = "partial"
                        if page.is_closed():
                            raise AdapterError(
                                "浏览器已关闭；本页结构已保存，图片未全部完成"
                            ) from None
                    finally:
                        bundle.finish("partial")
            if not bundle.nodes:
                bundle.error("tree", None, "未发现图层；可能是空页面、权限不足或网站结构已变化")
                return 2
            bundle.limitations.extend(
                [
                    "仅采集查看模式公开的图层树与标注；不包含设计文件内部二进制数据",
                    "未解析图层图标为节点类型，type 为 null；不猜测类型",
                    "未采集原型连线、组件变体定义与动画时间轴",
                    "PNG 为图层导出结果，不保证等同原始图片填充文件；字体二进制不随包下载",
                    f"图片导出策略：{args.export}；没有导出的节点以结构和 CSS 表示",
                ]
            )
            return 2 if bundle.errors else 0
        finally:
            context.close()


def main() -> int:
    args = parser().parse_args()
    configure(args)
    if args.command == "prepare":
        prepared = prepare_bundle(
            args.path, args.coordinate_mode, read_overrides(args.layout_overrides)
        )
        print(json.dumps(prepared, ensure_ascii=False))
        print(f"布局资料：{args.path.resolve() / 'layout.json'}；预览：preview.html")
        return 0
    if args.command == "validate":
        print(json.dumps(verify(args.path), ensure_ascii=False))
        return 0
    if args.command == "auth-export":
        try:
            size = export_auth(args.profile, args.channel, args.out)
        except (BrowserError, OSError, ValueError) as error:
            message = str(error) if isinstance(error, ValueError) else type(error).__name__
            print(f"登录态导出失败：{message}；请关闭同一 profile 的浏览器并确认已登录。")
            return 2
        print(f"登录态已保存：{args.out.resolve()}（{size} 字节）；请私下传输。")
        return 0
    if args.command == "login":
        if args.url != "https://mastergo.com":
            validate_url(args.url)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                args.profile.resolve(),
                channel=None if args.channel == "chromium" else args.channel,
                headless=False,
                accept_downloads=True,
            )
            try:
                context.pages[0].goto(args.url, wait_until="domcontentloaded", timeout=60000)
                input("请在浏览器自行完成登录，完成后在此按 Enter 保存会话并关闭：")
            finally:
                context.close()
        return 0
    url = args.url_file.read_text(encoding="utf-8").strip() if args.url_file else args.url
    if not url:
        url = input("请输入 MasterGo 设计链接：").strip()
    validate_url(url)
    if (
        args.max_nodes <= 0
        or args.max_tree_seconds <= 0
        or args.download_timeout_ms <= 0
        or (args.settle_ms < 0 or args.export_wait_ms < 0)
    ):
        raise ValueError("采集上限必须为正数，settle-ms 不得为负数")
    if args.auth_state:
        validate_auth(args.auth_state)
    bundle = Bundle(
        args.out, url, args.scope, args.coordinate_mode, read_overrides(args.layout_overrides)
    )
    try:
        result = crawl(args, url, bundle)
    except KeyboardInterrupt:
        bundle.error("interrupted", None, "用户中断采集")
        result = 130
    except (BrowserError, AdapterError, OSError) as error:
        message = str(error) if isinstance(error, AdapterError) else type(error).__name__
        bundle.error("browser", None, message)
        bundle.limitations.append("检查登录状态、文件查看/导出权限及浏览器安装情况")
        result = 2
    finally:
        # Always preserve partial evidence; no falsely successful empty bundle.
        bundle.finish("partial" if bundle.nodes else "blocked")
    if bundle.layout_overrides:
        try:
            prepare_bundle(args.out, args.coordinate_mode, bundle.layout_overrides)
        except ValueError:
            bundle.error("layout", None, "布局覆写引用未采集节点或资源；部分覆写未应用")
            bundle.finish("partial" if bundle.nodes else "blocked")
            result = 2
    write_json(
        args.out / "run.json", {"exit_code": result, "adapter": "mastergo-viewer-zh-2026-09-24"}
    )
    print(f"资料包：{args.out.resolve()}；节点 {len(bundle.nodes)}，资源 {len(bundle.assets)}")
    if result:
        print("存在采集失败或未完成步骤，详情见 manifest.json。")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        raise SystemExit(f"错误：{error}") from None
