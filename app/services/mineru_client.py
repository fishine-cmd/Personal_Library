"""HTTP client for a locally-running MinerU FastAPI service.

The user runs ``mineru-api`` themselves (default ``http://127.0.0.1:8000``);
this module just talks to it. We always go through ``/file_parse`` (the
synchronous endpoint) with the lightweight ``pipeline`` backend and request
both ``md_content`` (Markdown) and ``content_list`` (structured blocks) so
downstream heuristics can use whichever is more reliable.
"""

from __future__ import annotations

import json
from typing import Optional

import requests


class MineruError(RuntimeError):
    """Surface a user-friendly message for any MinerU failure."""


def _normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise MineruError("未配置 MinerU 服务地址")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def health_check(base_url: str, timeout: float = 3.0) -> dict:
    base = _normalize_base_url(base_url)
    try:
        resp = requests.get(f"{base}/health", timeout=timeout)
    except requests.RequestException as e:
        raise MineruError(f"无法连接到 MinerU ({base}): {e}") from e
    if resp.status_code != 200:
        raise MineruError(f"MinerU /health 返回 {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError:
        raise MineruError("MinerU /health 返回的不是 JSON")


def parse_pdf(
    base_url: str,
    file_bytes: bytes,
    filename: str,
    *,
    backend: str = "pipeline",
    lang: str = "ch",
    timeout: float = 600.0,
) -> dict:
    """Run the PDF through MinerU. Returns {'md': str, 'content_list': list}."""
    base = _normalize_base_url(base_url)
    files = {"files": (filename or "upload.pdf", file_bytes, "application/pdf")}
    data = {
        "backend": backend,
        "lang_list": lang,
        "parse_method": "auto",
        "formula_enable": "false",
        "table_enable": "false",
        "image_analysis": "false",
        "return_md": "true",
        "return_content_list": "true",
        "return_images": "false",
        "return_middle_json": "false",
        "return_model_output": "false",
        "response_format_zip": "false",
        "start_page_id": "0",
        "end_page_id": "2",  # only the first three pages — metadata lives there
    }
    try:
        resp = requests.post(f"{base}/file_parse", files=files, data=data, timeout=timeout)
    except requests.RequestException as e:
        raise MineruError(f"MinerU 请求失败: {e}") from e

    if resp.status_code != 200:
        raise MineruError(
            f"MinerU /file_parse 返回 {resp.status_code}: {resp.text[:1500]}"
        )

    payload = resp.json()
    results = payload.get("results") or {}
    if not results:
        raise MineruError("MinerU 返回的结果为空")

    _, first = next(iter(results.items()))
    md_text = first.get("md_content") or ""
    content_list_raw = first.get("content_list")
    content_list: list = []
    if content_list_raw:
        try:
            content_list = (
                json.loads(content_list_raw)
                if isinstance(content_list_raw, str)
                else content_list_raw
            )
        except json.JSONDecodeError:
            content_list = []
    return {"md": md_text, "content_list": content_list}
