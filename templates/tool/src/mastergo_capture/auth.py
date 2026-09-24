"""Portable MasterGo authentication; never serialize unrelated browser data."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, sync_playwright


def mastergo_host(host: str) -> bool:
    host = host.lower().lstrip(".")
    return host == "mastergo.com" or host.endswith(".mastergo.com")


def filter_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "cookies": [c for c in state["cookies"] if mastergo_host(c["domain"])],
        "origins": [
            origin
            for origin in state["origins"]
            if urlsplit(origin["origin"]).scheme == "https"
            and mastergo_host(urlsplit(origin["origin"]).hostname or "")
        ],
    }


def validate_auth(path: Path) -> None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError
        if not isinstance(state.get("cookies"), list) or not isinstance(state.get("origins"), list):
            raise ValueError
        filtered = filter_state(state)
        if filtered != state or not (state["cookies"] or state["origins"]):
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        raise ValueError(
            "登录态文件不可读、格式错误、为空或包含非 MasterGo 数据；请重新 auth-export"
        ) from None


def export_auth(profile: Path, channel: str, destination: Path) -> int:
    if not profile.is_dir():
        raise ValueError("浏览器目录不存在，请先执行 login")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            profile.resolve(), channel=None if channel == "chromium" else channel, headless=True
        )
        try:
            state = filter_state(dict(context.storage_state(indexed_db=True)))
        finally:
            context.close()
    if not (state["cookies"] or state["origins"]):
        raise ValueError("未找到 MasterGo 登录状态，请先执行 login")
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".auth-", dir=destination.parent)
    temporary = Path(name)
    try:
        # mkstemp creates mode 0600 on POSIX; never expose a partially written credential file.
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(payload)


@contextmanager
def capture_context(
    profile: Path, channel: str, headless: bool, auth_state: Path | None
) -> Iterator[BrowserContext]:
    with sync_playwright() as playwright:
        if auth_state is not None:
            validate_auth(auth_state)
            browser = playwright.chromium.launch(
                channel=None if channel == "chromium" else channel, headless=headless
            )
            try:
                context = browser.new_context(
                    storage_state=str(auth_state.resolve()),
                    accept_downloads=True,
                    viewport={"width": 1440, "height": 1000},
                )
                yield context
            finally:
                browser.close()
        else:
            context = playwright.chromium.launch_persistent_context(
                profile.resolve(),
                channel=None if channel == "chromium" else channel,
                headless=headless,
                accept_downloads=True,
                viewport={"width": 1440, "height": 1000},
            )
            try:
                yield context
            finally:
                context.close()
