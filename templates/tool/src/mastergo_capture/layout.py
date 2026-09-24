"""Derived layout contract. Observations, assumptions and author overrides stay distinct."""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .browser import css_values

MODES = ("unknown", "parent-relative", "root-relative", "canvas-absolute")
STYLE_KEYS = {
    "color",
    "background",
    "background-color",
    "border",
    "border-radius",
    "box-shadow",
    "font-family",
    "font-size",
    "font-weight",
    "line-height",
    "letter-spacing",
    "text-align",
    "white-space",
    "border-image",
    "opacity",
    "mix-blend-mode",
    "overflow",
    "visibility",
}
SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "policy", "roots", "nodes", "diagnostics"],
    "properties": {
        "schema_version": {"const": "1.0.0"},
        "policy": {"type": "object"},
        "roots": {"type": "array", "items": {"type": "string"}},
        "diagnostics": {"type": "array"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "parent_id",
                    "root_id",
                    "geometry",
                    "semantics",
                    "stacking",
                    "effects",
                    "assets",
                    "css",
                    "preview",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "parent_id": {"type": ["string", "null"]},
                    "root_id": {"type": "string"},
                    "geometry": {
                        "type": "object",
                        "required": ["absolute_bounds", "status", "source_space"],
                        "properties": {
                            "status": {
                                "enum": ["unknown", "derived", "overridden", "normalized_root"]
                            }
                        },
                    },
                    "semantics": {
                        "type": "object",
                        "required": ["role", "interactive", "source", "confidence"],
                    },
                    "stacking": {"type": "object", "required": ["z_index", "stack_path", "source"]},
                    "effects": {"type": "object"},
                    "assets": {
                        "type": "object",
                        "required": ["items", "composition", "selected_id"],
                    },
                    "css": {"type": "object", "required": ["observed", "recovered", "generated"]},
                    "preview": {"type": "object"},
                },
            },
        },
    },
}

RECT: dict[str, Any] = {
    "type": ["object", "null"],
    "required": ["x", "y", "width", "height"],
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "width": {"type": "number", "minimum": 0},
        "height": {"type": "number", "minimum": 0},
    },
    "additionalProperties": False,
}
layout_fields = SCHEMA["properties"]["nodes"]["items"]["properties"]
layout_fields["geometry"]["properties"].update(
    absolute_bounds=RECT,
    candidate_parent_relative_bounds=RECT,
    source_space={"enum": list(MODES)},
)
layout_fields["semantics"]["properties"] = {
    "role": {"type": "string"},
    "interactive": {"type": ["boolean", "null"]},
    "source": {"enum": ["heuristic", "override"]},
}
layout_fields["stacking"]["properties"] = {
    "z_index": {"type": "integer"},
    "stack_path": {"type": "array", "items": {"type": "integer"}},
    "paint_order": {"type": "integer", "minimum": 0},
}

GUIDE = (Path(__file__).resolve().parents[2] / "references/layout-consumption.md").read_text(
    encoding="utf-8"
)


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?(?:px)?", value.strip()):
        result = float(value.strip().removesuffix("px"))
        return result if math.isfinite(result) else None
    return None


def read_overrides(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_overrides(data)
    return dict(data)


def validate_overrides(data: Any) -> None:
    if not isinstance(data, dict) or set(data) - {"coordinate_mode", "nodes"}:
        raise ValueError("布局覆写必须包含 coordinate_mode 或 nodes")
    if data.get("coordinate_mode", "unknown") not in MODES or not isinstance(
        data.get("nodes", {}), dict
    ):
        raise ValueError("布局覆写的坐标模式或 nodes 无效")
    for node_id, node in data.get("nodes", {}).items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise ValueError("布局覆写需要节点 ID 到属性对象的映射")
        allowed = {
            "coordinate_space",
            "absolute_bounds",
            "role",
            "interactive",
            "z_index",
            "asset_id",
        }
        if set(node) - allowed or node.get("coordinate_space", "unknown") not in MODES:
            raise ValueError("布局覆写包含不支持的字段或坐标模式")
        if "absolute_bounds" in node:
            bounds = node["absolute_bounds"]
            if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
                raise ValueError("absolute_bounds 必须含 x/y/width/height")
            if any(number(v) is None or not isinstance(v, (int, float)) for v in bounds.values()):
                raise ValueError("absolute_bounds 必须为有限数值")
            if bounds["width"] < 0 or bounds["height"] < 0:
                raise ValueError("absolute_bounds 的尺寸不得为负数")
        if "interactive" in node and not isinstance(node["interactive"], bool):
            raise ValueError("interactive 必须为布尔值")
        if "z_index" in node and (type(node["z_index"]) is not int):
            raise ValueError("z_index 必须为整数")
        for key in ("role", "asset_id"):
            if key in node and not isinstance(node[key], str):
                raise ValueError(f"{key} 必须为字符串")


def role_for(node: dict[str, Any], css: dict[str, str]) -> dict[str, Any]:
    name = node["name"].lower()
    role, evidence = "unknown", "无可用语义证据"
    for pattern, candidate in [
        (r"蒙版|mask", "mask-candidate"),
        (r"按钮|button|可点击", "button"),
        (r"标题|title", "title"),
        (r"歌词|lyrics", "text-overlay"),
        (r"背景|background|(?:^|_)bg$", "background"),
        (r"封面|图片|image|cover|唱片", "image"),
    ]:
        if re.search(pattern, name):
            role, evidence = candidate, f"name 匹配 {pattern}"
            break
    if role == "unknown":
        if (node.get("design") or {}).get("text") is not None or "font-size" in css:
            role, evidence = "text", "文字内容或 font-size"
        elif node.get("children"):
            role, evidence = "container", "包含子节点"
        elif node.get("asset_ids"):
            role, evidence = "image", "包含导出资源"
    return {
        "role": role,
        "interactive": None,
        "source": "heuristic",
        "confidence": "low",
        "evidence": evidence,
    }


def build_layout(
    nodes: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    mode: str = "unknown",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    overrides = overrides or {}
    validate_overrides(overrides)
    mode = overrides.get("coordinate_mode", mode)
    if mode not in MODES:
        raise ValueError("不支持的坐标模式")
    by_id = {node["id"]: node for node in nodes}
    settings = overrides.get("nodes", {})
    if set(settings) - set(by_id):
        raise ValueError("布局覆写引用不存在的节点 ID")
    asset_index = {asset["id"]: asset for asset in assets}
    resolved: dict[str, dict[str, Any]] = {}
    visiting: set[str] = set()
    diagnostics: list[dict[str, str]] = []
    siblings: dict[str | None, list[dict[str, Any]]] = {}
    for node in nodes:
        siblings.setdefault(node.get("parent_id"), []).append(node)
    sibling_positions: dict[str, int] = {}
    for group in siblings.values():
        group.sort(key=lambda n: n["order"])
        sibling_positions.update({node["id"]: i for i, node in enumerate(group)})

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        ident = node["id"]
        if ident in resolved:
            return resolved[ident]
        if ident in visiting:
            raise ValueError("布局图层树存在环")
        visiting.add(ident)
        parent_id = node.get("parent_id")
        parent = resolve(by_id[parent_id]) if parent_id in by_id else None
        root_id = parent["root_id"] if parent else ident
        design = node.get("design") or {}
        observed = design.get("css_properties", {})
        original_css = design.get("css", "")
        repaired_css = re.sub(r"(?<![;{\s/])\s*\n(?=\s*[\w-]+\s*:)", ";\n", original_css)
        recovered = css_values(repaired_css) if repaired_css != original_css else {}
        css = {**observed, **recovered}
        bounds = design.get("bounds") or {}
        raw = {
            key: number(bounds.get(key))
            if number(bounds.get(key)) is not None
            else number(css.get(prop))
            for key, prop in [("x", "left"), ("y", "top"), ("width", "width"), ("height", "height")]
        }
        override = settings.get(ident, {})
        space = override.get("coordinate_space", mode)
        absolute = None
        candidate = None
        status = "unknown"
        width, height = raw["width"], raw["height"]
        transform = css.get("transform")
        transform_unresolved = transform not in (None, "none") or bool(
            parent and parent["geometry"]["unresolved_transform"]
        )
        if "absolute_bounds" in override:
            absolute = dict(override["absolute_bounds"])
            if not parent_id and (absolute["x"] != 0 or absolute["y"] != 0):
                raise ValueError("采集根的 absolute_bounds 原点必须为 0,0")
            status = "overridden"
            transform_unresolved = False
        elif width is not None and height is not None and width >= 0 and height >= 0:
            if not parent and not parent_id and not transform_unresolved:
                absolute = {"x": 0, "y": 0, "width": width, "height": height}
                status = "normalized_root"
            elif (
                parent
                and raw["x"] is not None
                and raw["y"] is not None
                and not transform_unresolved
            ):
                parent_box = parent["geometry"]["absolute_bounds"]
                parent_candidate = (
                    parent_box or parent["geometry"]["candidate_parent_relative_bounds"]
                )
                if parent_candidate:
                    candidate = {
                        **raw,
                        "x": parent_candidate["x"] + raw["x"],
                        "y": parent_candidate["y"] + raw["y"],
                    }
                if space == "parent-relative" and parent_box:
                    absolute = candidate
                elif space == "root-relative":
                    absolute = dict(raw)
                elif space == "canvas-absolute":
                    root_raw = resolved[root_id]["geometry"]["raw_bounds"]
                    if root_raw["x"] is not None and root_raw["y"] is not None:
                        absolute = {
                            **raw,
                            "x": raw["x"] - root_raw["x"],
                            "y": raw["y"] - root_raw["y"],
                        }
                if absolute:
                    status = "derived"
        geometry = {
            "raw_bounds": raw,
            "raw_sources": {
                key: "inspector_bounds"
                if number(bounds.get(key)) is not None
                else "recovered_css"
                if prop in recovered
                else "observed_css"
                if number(css.get(prop)) is not None
                else "not_collected"
                for key, prop in [
                    ("x", "left"),
                    ("y", "top"),
                    ("width", "width"),
                    ("height", "height"),
                ]
            },
            "source_space": space,
            "absolute_bounds": absolute,
            "candidate_parent_relative_bounds": candidate,
            "status": status,
            "confidence": "conditional" if status == "derived" else status,
            "unit": "px",
            "unresolved_transform": transform_unresolved,
        }
        semantic = role_for(node, css)
        if "role" in override:
            semantic.update(
                role=override["role"],
                source="override",
                confidence="user_supplied",
                evidence="layout overrides",
            )
        semantic["interactive"] = override.get("interactive")
        semantic["interactive_source"] = (
            "override" if "interactive" in override else "not_collected"
        )
        group = siblings[parent_id]
        sibling_index = sibling_positions[ident]
        fallback_z = len(group) - sibling_index - 1
        css_z = css.get("z-index", "")
        z = int(css_z) if re.fullmatch(r"-?\d+", css_z) else fallback_z
        z_source = (
            "observed_css" if re.fullmatch(r"-?\d+", css_z) else "tree_top_is_front_assumption"
        )
        if (
            z_source == "observed_css"
            and "z-index" in recovered
            and recovered.get("z-index") != observed.get("z-index")
        ):
            z_source = "recovered_css"
        if "z_index" in override:
            z, z_source = override["z_index"], "override"
        stack_path = (parent["stacking"]["stack_path"] if parent else []) + [z]
        node_assets = [
            asset_index[a]
            for a in node.get("asset_ids", [])
            if a in asset_index and asset_index[a]["role"] == "design_export"
        ]
        selected = node_assets[0]["id"] if len(node_assets) == 1 else None
        if "asset_id" in override:
            if override["asset_id"] not in {a["id"] for a in node_assets}:
                raise ValueError("覆写的 asset_id 不属于该节点")
            selected = override["asset_id"]
        items = [
            {
                "id": a["id"],
                "path": a["path"],
                "width": a.get("width"),
                "height": a.get("height"),
                "original_name": a.get("original_name"),
                "download_order": i,
                "paint_order": None,
                "offset": None,
                "usage": "node_export_candidate",
            }
            for i, a in enumerate(node_assets)
        ]
        generated: dict[str, str] = {}
        if absolute:
            generated = {
                "position": "absolute",
                "left": f"{absolute['x']:g}px",
                "top": f"{absolute['y']:g}px",
                "width": f"{absolute['width']:g}px",
                "height": f"{absolute['height']:g}px",
                "z-index": str(z),
            }
        local_css = dict(generated)
        if parent:
            parent_box = parent["geometry"]["absolute_bounds"]
            if absolute and parent_box:
                local_css.update(
                    left=f"{absolute['x'] - parent_box['x']:g}px",
                    top=f"{absolute['y'] - parent_box['y']:g}px",
                )
            else:
                local_css = {}
        asset = asset_index.get(selected) if selected else None
        # Do not stretch trimmed text exports or shadow-expanded images to the design rectangle.
        raster_ok = bool(
            asset
            and absolute
            and asset["format"] == "png"
            and all(
                number(asset.get(key)) is not None and abs(asset[key] - absolute[key]) <= 1
                for key in ("width", "height")
            )
        )
        result = {
            "id": ident,
            "name": node["name"],
            "parent_id": parent_id,
            "root_id": root_id,
            "page_id": node["page_id"],
            "children": node.get("children", []),
            "text": design.get("text"),
            "geometry": geometry,
            "semantics": semantic,
            "stacking": {
                "z_index": z,
                "source": z_source,
                "sibling_tree_index": sibling_index,
                "stack_path": stack_path,
                "scope": "parent",
                "paint_order": None,
            },
            "effects": {
                key: css.get(key)
                for key in (
                    "opacity",
                    "mix-blend-mode",
                    "mask",
                    "mask-image",
                    "clip-path",
                    "overflow",
                    "transform",
                )
            },
            "assets": {
                "items": items,
                "selected_id": selected,
                "selection_source": "override"
                if "asset_id" in override
                else "unique_export"
                if selected
                else "unresolved",
                "composition": "multiple_unresolved"
                if len(items) > 1
                else "single_node_export"
                if items
                else "none",
            },
            "css": {
                "observed": observed,
                "recovered": recovered,
                "generated": generated,
                "generated_coordinate_space": "capture_root",
                "generated_parent_relative": local_css,
                "issues": ["missing_semicolon_recovery"] if recovered else [],
            },
            "preview": {
                "mode": "composite_image"
                if raster_ok
                else "structure"
                if absolute
                else "unpositioned",
                "assumptions": ["export_aligns_with_node_bounds"] if raster_ok else [],
                "asset_id": selected if raster_ok else None,
            },
        }
        for issue, enabled in [
            ("coordinate_unresolved", absolute is None),
            ("multiple_assets_unresolved", len(items) > 1 and "asset_id" not in override),
            ("export_bounds_mismatch", bool(asset and absolute and not raster_ok)),
            ("css_recovered", bool(recovered)),
            (
                "complex_effect_requires_reference",
                any(
                    css.get(k) not in (None, "none")
                    for k in ("mask", "mask-image", "clip-path", "transform")
                ),
            ),
            ("mask_relation_unresolved", semantic["role"] == "mask-candidate"),
        ]:
            if enabled:
                diagnostics.append({"node_id": ident, "code": issue})
        resolved[ident] = result
        visiting.remove(ident)
        return result

    for node in nodes:
        resolve(node)
    flat = [resolved[node["id"]] for node in nodes]
    # Explicit order for Agent consumption, grouped by parent, never a global z-index.
    for group in siblings.values():
        paint = sorted(
            (resolved[n["id"]] for n in group),
            key=lambda n: (n["stacking"]["z_index"], -n["stacking"]["sibling_tree_index"]),
        )
        for index, item in enumerate(paint):
            item["stacking"]["paint_order"] = index
    result = {
        "schema_version": "1.0.0",
        "policy": {
            "coordinate_mode": mode,
            "coordinates_verified": False,
            "tree_order": "top_is_front_assumption",
            "preview_strategy": "composite_first_no_duplicate_descendants",
            "visibility_and_component_variant_state": "not_collected",
            "skeleton_fidelity": "unverified_structure_only",
        },
        "overrides": overrides,
        "roots": [n["id"] for n in flat if not n["parent_id"]],
        "nodes": flat,
        "diagnostics": diagnostics,
    }
    Draft202012Validator(SCHEMA).validate(result)
    return result


def safe_style(css: dict[str, str]) -> str:
    # Whitelist property names and prevent URL fetching, declaration breakout and HTML injection.
    return ";".join(
        f"{key}:{value}"
        for key, value in css.items()
        if key in STYLE_KEYS
        and not re.search(r"url\s*\(|expression|[;{}<>\\\x00-\x1f]", value, re.I)
    )


def render_preview(layout: dict[str, Any], strategy: str = "composite_first") -> str:
    by_id = {node["id"]: node for node in layout["nodes"]}
    omitted: list[str] = []

    def render(node: dict[str, Any], parent_box: dict[str, Any] | None = None) -> str:
        box = node["geometry"]["absolute_bounds"]
        if box is None or (
            node["semantics"]["role"] == "mask-candidate"
            and node["semantics"]["source"] != "override"
        ):
            omitted.append(node["id"])
            return ""
        x = box["x"] - (parent_box["x"] if parent_box else 0)
        y = box["y"] - (parent_box["y"] if parent_box else 0)
        style = (
            f"position:absolute;left:{x:g}px;top:{y:g}px;"
            f"width:{box['width']:g}px;height:{box['height']:g}px;"
            f"z-index:{node['stacking']['z_index']};isolation:isolate;box-sizing:border-box;"
        )
        content = ""
        if node["preview"]["mode"] == "composite_image" and (
            strategy == "composite_first" or not node["children"]
        ):
            asset = next(
                a for a in node["assets"]["items"] if a["id"] == node["preview"]["asset_id"]
            )
            path = asset["path"]
            if not re.fullmatch(r"assets/[a-f0-9]{64}\.png", path):
                raise ValueError("预览资源路径无效")
            content = f'<img src="{path}" alt="" style="display:block;width:100%;height:100%">'
        else:
            style += safe_style({**node["css"]["observed"], **node["css"]["recovered"]})
            if node["text"] is not None:
                content += (
                    '<span style="white-space:pre-wrap">' + html.escape(node["text"]) + "</span>"
                )
            children = sorted(
                (by_id[c] for c in node["children"] if c in by_id),
                key=lambda n: n["stacking"]["paint_order"],
            )
            content += "".join(render(child, box) for child in children)
        return (
            f'<div data-node-id="{html.escape(node["id"], quote=True)}" '
            f'style="{html.escape(style, quote=True)}">{content}</div>'
        )

    sections = []
    for ident in layout["roots"]:
        root = by_id[ident]
        box = root["geometry"]["absolute_bounds"]
        if box:
            sections.append(
                f'<section><h2>{html.escape(root["name"])}</h2><div class="canvas" '
                f'style="width:{box["width"]:g}px;height:{box["height"]:g}px">'
                f"{render(root)}</div></section>"
            )
        else:
            omitted.append(ident)
    layout["preview" if strategy == "composite_first" else "skeleton"] = {
        "omitted_node_ids": omitted,
        "strategy": strategy,
        "uses_candidate_coordinates": False,
    }
    return (
        '<!doctype html><html lang="zh"><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src 'self' data:; style-src 'unsafe-inline'\"><title>布局预览</title>"
        "<style>body{font:14px system-ui;background:#242424;color:#eee;padding:24px}"
        ".canvas{position:relative;background:repeating-conic-gradient("
        "#333 0% 25%,#393939 0% 50%) 0/20px 20px;margin-bottom:32px}"
        "h2{font-size:16px}section{margin-bottom:32px}</style><h1>静态布局预览</h1>"
        "<p>模式：" + strategy + "。composite_first 优先使用复合 PNG；layers 展开为节点骨架。"
        "坐标未确认的节点不定位；复杂遮罩与字体需对照原图。</p><p>未定位的可见分支："
        + str(len(omitted))
        + "；完整缺失项、坐标假设与效果见 layout.json / LAYOUT_GUIDE.md。</p>"
        + "".join(sections)
        + "</html>"
    )
