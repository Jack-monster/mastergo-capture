"""MasterGo viewer DOM adapter, observed against the Chinese viewer on 2026-09-24.

Only reads rendered DOM and clicks viewer controls. No private application stores,
cookies extraction, network response interception, or undocumented HTTP APIs.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import tinycss2
from playwright.sync_api import Page

ROW = ".tree_layout [data-id]"
SCROLL = ".layer_tree .scrollbody"
PAGE_ITEM = ".layer_content_page"

READ_ROWS = """els => els.map(e => {
 const arrow=e.querySelector('.arrow_icon');
 return {id:e.dataset.id, name:e.querySelector('.item_name')?.textContent || '',
 depth:Number(e.dataset.offsetleft), closed:e.dataset.isclose==='true',
 expandable:!!arrow && getComputedStyle(arrow).visibility!=='hidden',
 fixed:e.classList.contains('container-fixed'),
 y:new DOMMatrixReadOnly(e.style.transform).m42};
}).sort((a,b)=>a.y-b.y)"""


class AdapterError(RuntimeError):
    pass


def layer_selector(node_id: str) -> str:
    if not re.fullmatch(r"[\w:./-]+", node_id):
        raise AdapterError("不支持的图层 ID 字符")
    return f'{ROW}[data-id="{node_id}"]'


def node_url(url: str, node_id: str) -> str:
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    params["layer_id"] = [node_id]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params, doseq=True), ""))


def css_values(css: str) -> dict[str, str]:
    """Extract simple declarations for indexing, retaining full CSS as evidence."""
    result: dict[str, str] = {}
    for declaration in tinycss2.parse_declaration_list(
        css, skip_comments=True, skip_whitespace=True
    ):
        if declaration.type == "declaration":
            result[declaration.name] = tinycss2.serialize(declaration.value).strip()
    return result


def inspector_bounds(sections: list[dict[str, Any]]) -> dict[str, Any]:
    bounds: dict[str, Any] = {
        "x": None,
        "y": None,
        "width": None,
        "height": None,
        "unit": "px",
        "coordinate_space": "as_displayed_by_mastergo",
    }
    labels = {"X": "x", "Y": "y", "W": "width", "H": "height"}
    for section in sections:
        for row in section["rows"]:
            if row["label"] not in {"位置", "尺寸"}:
                continue
            for label, number in re.findall(r"([XYWH])\s+(-?[0-9]+(?:\.[0-9]+)?)px", row["value"]):
                bounds[labels[label]] = float(number)
    return bounds


def hierarchy(rows: list[dict[str, Any]], page_id: str) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda r: r["y"])
    nodes: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for order, row in enumerate(ordered):
        while stack and stack[-1]["tree_depth"] >= row["depth"]:
            stack.pop()
        node = {
            "id": row["id"],
            "page_id": page_id,
            "name": row["name"],
            "parent_id": stack[-1]["id"] if stack else None,
            "children": [],
            "order": order,
            "tree_depth": row["depth"],
            "type": None,
            "has_children_in_ui": row["expandable"],
            "design": None,
            "asset_ids": [],
            "evidence_path": None,
            "capture_status": "pending",
        }
        if stack:
            stack[-1]["children"].append(node["id"])
        nodes.append(node)
        stack.append(node)
    return nodes


class MasterGoViewer:
    def __init__(
        self,
        page: Page,
        settle_ms: int = 180,
        export_wait_ms: int = 5000,
        download_timeout_ms: int = 30000,
    ) -> None:
        self.page = page
        self.settle_ms = settle_ms
        self.export_wait_ms = export_wait_ms
        self.download_timeout_ms = download_timeout_ms
        self.page.set_default_timeout(8000)

    def open(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.locator(".layer_tree").wait_for(state="visible", timeout=60000)
        self.page.locator(ROW).first.wait_for(state="attached", timeout=60000)
        self.page.wait_for_timeout(self.settle_ms)

    def pages(self) -> list[dict[str, Any]]:
        # Expand page folders only; this affects viewer UI, not the design document.
        for _ in range(100):
            closed = self.page.locator(
                ".master-tree-item:has(.layer_content:not(.layer_content_page)) "
                ".master-tree-item__expand__icon:not(.master-tree-item__expand__icon--open)"
            )
            if not closed.count():
                break
            closed.first.click()
            self.page.wait_for_timeout(self.settle_ms)
        return [
            {"index": i, "name": name.strip()}
            for i, name in enumerate(self.page.locator(PAGE_ITEM).all_text_contents())
        ]

    def select_page(self, index: int) -> str:
        item = self.page.locator(PAGE_ITEM).nth(index)
        already_current = item.locator(".highlight").count() > 0
        old_id = parse_qs(urlsplit(self.page.url).query).get("page_id", [""])[0]
        old_first = (
            self.page.locator(ROW).first.get_attribute("data-id")
            if self.page.locator(ROW).count()
            else None
        )
        item.click()
        if not already_current:
            self.page.wait_for_function(
                "old => new URL(location.href).searchParams.get('page_id') !== old",
                arg=old_id,
                timeout=15000,
            )
            if old_first:
                self.page.wait_for_function(
                    "old => document.querySelector('.tree_layout [data-id]')?.dataset.id !== old",
                    arg=old_first,
                    timeout=15000,
                )
        self.page.wait_for_timeout(max(self.settle_ms, 500))
        page_ids = parse_qs(urlsplit(self.page.url).query).get("page_id", [])
        if not page_ids:
            raise AdapterError("页面切换后 URL 未提供 page_id")
        return page_ids[0]

    def rows(self) -> list[dict[str, Any]]:
        value: list[dict[str, Any]] = self.page.locator(ROW).evaluate_all(READ_ROWS)
        return value

    def scan_tree(
        self,
        max_nodes: int,
        root_id: str | None = None,
        max_seconds: int = 600,
        expand_collapsed: bool = True,
    ) -> tuple[list[dict[str, Any]], bool]:
        scroll = self.page.locator(SCROLL)
        root_y = 0.0
        root_depth = -1
        scroll.evaluate("e=>e.scrollTop=0")
        if root_id:
            # Sticky ancestors use viewport coordinates; find the real row by scrolling.
            for _ in range(1000):
                self.page.wait_for_timeout(self.settle_ms)
                root_row = next(
                    (r for r in self.rows() if r["id"] == root_id and not r["fixed"]), None
                )
                if root_row:
                    root_y, root_depth = root_row["y"], root_row["depth"]
                    break
                metrics = scroll.evaluate("e=>[e.scrollTop,e.clientHeight,e.scrollHeight]")
                if metrics[0] + metrics[1] >= metrics[2] - 2:
                    raise AdapterError("链接指向的图层未出现在已展开的图层树中")
                scroll.evaluate("e=>e.scrollTop+=e.clientHeight*0.75")
            else:
                raise AdapterError("定位图层超过滚动上限")
        scroll.evaluate("(e,y)=>e.scrollTop=Math.max(0,y-60)", root_y)
        known: dict[str, dict[str, Any]] = {}
        deadline = time.monotonic() + max_seconds
        previous_bottom: tuple[int, int, int] | None = None
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(self.settle_ms)
            visible = self.rows()
            candidates = []
            boundary = False
            for row in visible:
                if row["fixed"] or row["y"] < root_y:
                    continue
                if root_id and row["id"] != root_id and row["depth"] <= root_depth:
                    boundary = True
                    break
                candidates.append(row)
            for row in candidates:
                if row["id"] not in known and len(known) >= max_nodes:
                    return list(known.values()), False
                known[row["id"]] = row
            if expand_collapsed:
                collapsed = next((r for r in candidates if r["expandable"] and r["closed"]), None)
                if collapsed:
                    locator = self.page.locator(layer_selector(collapsed["id"]))
                    locator.locator(".arrow_icon").click()
                    self.page.wait_for_function(
                        "selector => document.querySelector(selector) && "
                        "document.querySelector(selector).dataset.isclose!=='true'",
                        arg=layer_selector(collapsed["id"]),
                        timeout=8000,
                    )
                    continue
            metrics = scroll.evaluate(
                "e=>({top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight})"
            )
            at_bottom = metrics["top"] + metrics["height"] >= metrics["total"] - 2
            if boundary or at_bottom:
                marker = (len(known), int(metrics["total"]), int(metrics["top"]))
                if marker == previous_bottom:
                    return list(known.values()), True
                previous_bottom = marker
                continue
            scroll.evaluate("e=>e.scrollTop += Math.max(100,e.clientHeight*0.75)")
        return list(known.values()), False

    def select_node(self, node_id: str, y: float) -> None:
        self.page.locator(SCROLL).evaluate("(e,y)=>e.scrollTop=Math.max(0,y-80)", y)
        locator = self.page.locator(layer_selector(node_id))
        locator.locator(".item_name").click()
        self.page.wait_for_function(
            "selector => document.querySelector(selector)?.classList"
            ".contains('container__checked')",
            arg=layer_selector(node_id),
            timeout=8000,
        )
        self.page.wait_for_timeout(self.settle_ms)
        title = self.page.locator(".observe-title")
        if not title.count():
            raise AdapterError("标注面板未出现；请使用只读查看模式")
        name = locator.locator(".item_name").inner_text().strip()
        if title.inner_text().strip() != name:
            raise AdapterError("标注标题与所选图层不一致，拒绝关联到错误节点")

    def inspector(self) -> dict[str, Any]:
        sections: list[dict[str, Any]] = self.page.locator(".observe-info").evaluate_all(
            """els=>els.map(e=>({text:e.innerText,
            rows:[...e.querySelectorAll('.observe-info__cell')].map(r=>({
             label:r.querySelector('.observe-info__label')?.innerText.trim() ||
                   r.querySelector('.observe-info__title')?.innerText.trim() || '',
             value:r.querySelector('.observe-info__content')?.innerText || ''}))}))"""
        )
        css = (
            self.page.locator("#code-box").inner_text()
            if self.page.locator("#code-box").count()
            else ""
        )
        declarations = css_values(css)
        return {
            "name": self.page.locator(".observe-title").inner_text(),
            "sections": sections,
            "css": css,
            "css_properties": declarations,
            "bounds": inspector_bounds(sections),
            "text_content": next(
                (s["text"].split("\n", 1)[1] for s in sections if s["text"].startswith("内容\n")),
                None,
            ),
            "coordinate_space": "as_displayed_by_mastergo",
            "source": "mastergo_viewer_inspector",
        }

    def export_png(self) -> tuple[bytes, str, dict[str, str]]:
        # Canvas export readiness lags behind inspector DOM readiness in the viewer.
        self.page.wait_for_timeout(self.export_wait_ms)
        panel = self.page.locator(".right-export")
        panel.wait_for(state="visible")
        if not panel.locator(".right-export-item").count():
            panel.locator(".add-export-item-button").click()
        item = panel.locator(".right-export-item").first
        file_format = item.locator("input[readonly]").first
        if file_format.input_value() != "PNG":
            file_format.click()
            self.page.get_by_text("PNG", exact=True).filter(visible=True).click()
        scale = item.locator("input").first
        scale.fill("1x")
        scale.press("Enter")
        self.page.wait_for_timeout(self.settle_ms)
        if file_format.input_value() != "PNG":
            raise AdapterError("未能切换为 PNG 导出")
        with self.page.expect_download(timeout=self.download_timeout_ms) as info:
            panel.locator(".export-button").click()
        download = info.value
        failure = download.failure()
        if failure:
            raise AdapterError(f"浏览器下载失败：{failure[:120]}")
        path = download.path()
        if path is None:
            raise AdapterError("下载未产生本地文件")
        return (
            path.read_bytes(),
            download.suggested_filename,
            {"format": "PNG", "scale": scale.input_value()},
        )
