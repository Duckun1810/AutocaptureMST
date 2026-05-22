"""Giải captcha 5 ký tự (a-z, 0-9) bằng LLM Qwen-VL qua DashScope.

Dùng OpenAI-compatible endpoint của Alibaba để gọi Qwen-VL model.
API key đọc từ .env (DASHSCOPE_API_KEY).

Captcha của trang là PNG **RGBA** (alpha channel). LLM xử lý OK alpha,
nhưng để tăng độ chắc chắn ta flatten về RGB nền trắng trước khi gửi.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI
from PIL import Image

from src.config import (
    CAPTCHA_CHARSET,
    CAPTCHA_LENGTH,
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    DASHSCOPE_MODEL,
    LLM_TIMEOUT_SEC,
)

_VALID_PATTERN = re.compile(rf"^[{re.escape(CAPTCHA_CHARSET)}]{{{CAPTCHA_LENGTH}}}$")

_PROMPT = (
    f"This image is a CAPTCHA containing exactly {CAPTCHA_LENGTH} characters. "
    f"The characters are only lowercase English letters (a-z) and digits (0-9). "
    f"Read the characters from left to right and respond with ONLY those "
    f"{CAPTCHA_LENGTH} characters in a single line, no spaces, no punctuation, "
    f"no explanation. Example valid response: 'a3k9x'."
)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not DASHSCOPE_API_KEY:
            raise RuntimeError(
                "DASHSCOPE_API_KEY chưa được set. Copy .env.example thành .env và điền key."
            )
        _client = OpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
            timeout=LLM_TIMEOUT_SEC,
        )
    return _client


def _flatten_to_png(image_bytes: bytes) -> bytes:
    """Flatten ảnh về RGB nền trắng để LLM nhìn rõ nhất, output PNG."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[3])
        img = bg
    else:
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _extract_candidate(text: str) -> Optional[str]:
    """Tìm chuỗi đúng pattern trong response. LLM có thể trả thêm text dù đã yêu cầu only chars."""
    cleaned = text.strip().lower()
    if _VALID_PATTERN.match(cleaned):
        return cleaned
    # Fallback: tìm substring khớp pattern (model đôi khi trả 'The code is: a3k9x.')
    match = re.search(rf"[{re.escape(CAPTCHA_CHARSET)}]{{{CAPTCHA_LENGTH}}}", cleaned)
    if match:
        return match.group(0)
    return None


def solve(image_bytes: bytes, debug_dir: Optional[Path] = None, tag: str = "") -> Optional[str]:
    """OCR captcha bằng Qwen-VL. Trả về chuỗi 5 ký tự [a-z0-9] hoặc None."""
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{tag}_raw.png").write_bytes(image_bytes)

    try:
        flat = _flatten_to_png(image_bytes)
    except Exception:
        return None

    if debug_dir is not None:
        (debug_dir / f"{tag}_flat.png").write_bytes(flat)

    b64 = base64.b64encode(flat).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=DASHSCOPE_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
            temperature=0,
            max_tokens=20,
        )
    except Exception as e:
        if debug_dir is not None:
            (debug_dir / f"{tag}_error.txt").write_text(str(e), encoding="utf-8")
        return None

    if not resp.choices:
        return None
    raw = resp.choices[0].message.content or ""

    if debug_dir is not None:
        (debug_dir / f"{tag}_response.txt").write_text(raw, encoding="utf-8")

    return _extract_candidate(raw)
