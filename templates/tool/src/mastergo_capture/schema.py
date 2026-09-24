"""Versioned per-file schema for Agent consumption."""

from typing import Any

NODE: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "name",
        "page_id",
        "parent_id",
        "children",
        "order",
        "design",
        "capture_status",
        "asset_ids",
    ],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "page_id": {"type": "string"},
        "parent_id": {"type": ["string", "null"]},
        "children": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "order": {"type": "integer", "minimum": 0},
        "design": {"type": ["object", "null"]},
        "capture_status": {"enum": ["pending", "properties_captured", "captured", "partial"]},
        "asset_ids": {"type": "array", "items": {"type": "string"}},
    },
}
ASSET: dict[str, Any] = {
    "type": "object",
    "required": ["id", "node_id", "path", "sha256", "bytes", "role", "format"],
    "properties": {
        "id": {"type": "string"},
        "node_id": {"type": "string"},
        "path": {"type": "string", "pattern": r"^assets/[a-f0-9]{64}\.[a-z]+$"},
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "bytes": {"type": "integer", "minimum": 1},
        "role": {"enum": ["design_export", "editor_screenshot"]},
        "format": {"enum": ["png", "jpg", "gif", "webp", "svg"]},
    },
}
PAGE: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name", "node_ids", "root_ids", "tree_complete"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "node_ids": {"type": "array", "items": {"type": "string"}},
        "root_ids": {"type": "array", "items": {"type": "string"}},
        "tree_complete": {"type": "boolean"},
    },
}
FILES: dict[str, dict[str, Any]] = {
    "nodes.json": {"type": "array", "items": NODE},
    "assets.json": {"type": "array", "items": ASSET},
    "pages.json": {"type": "array", "items": PAGE},
    "interactions.json": {"type": "object", "required": ["status", "transitions", "unknowns"]},
}
