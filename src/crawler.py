"""Logic Playwright: mở trang, fill form, tải captcha, click submit, screenshot."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright

from src import captcha_solver, parser
from src.config import (
    CAPTCHA_DEBUG_SUBDIR,
    MAX_CAPTCHA_RETRY,
    NAV_TIMEOUT_MS,
    SCREENSHOT_SUBDIR,
    SEL_CAPTCHA_IMG,
    SEL_CAPTCHA_INPUT,
    SEL_MST_INPUT,
    SEL_SUBMIT_BTN,
    resolve_url,
)


@dataclass
class CrawlOutcome:
    mst: str
    status: str
    rows: list
    screenshot_path: Optional[str]
    retry_count: int
    message: Optional[str]
    timestamp: str
    tab: str = ""  # "DN" (mstdn.jsp) hoặc "TNCN" (mstcn.jsp)


class MSTCrawler:
    def __init__(self, output_dir: Path, debug: bool = False, max_retry: int = MAX_CAPTCHA_RETRY):
        self.output_dir = Path(output_dir)
        self.debug = debug
        self.max_retry = max_retry
        self.screenshot_dir = self.output_dir / SCREENSHOT_SUBDIR
        self.captcha_debug_dir = self.output_dir / CAPTCHA_DEBUG_SUBDIR
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        if debug:
            self.captcha_debug_dir.mkdir(parents=True, exist_ok=True)

        self._pw = None
        self._browser = None
        self._context = None
        self._page: Optional[Page] = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.debug)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(NAV_TIMEOUT_MS)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def lookup(self, mst: str) -> CrawlOutcome:
        assert self._page is not None
        page = self._page
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url = resolve_url(mst)
        tab = "DN" if url.endswith("mstdn.jsp") else "TNCN"

        try:
            page.goto(url, wait_until="networkidle")
        except PWTimeoutError as e:
            return CrawlOutcome(mst, "ERROR", [], None, 0, f"goto timeout: {e}", timestamp, tab)

        last_message = None
        for attempt in range(1, self.max_retry + 1):
            page.fill(SEL_MST_INPUT, mst)

            captcha_text = self._solve_current_captcha(page, mst, attempt)
            if not captcha_text:
                last_message = "OCR failed local validation"
                continue

            page.fill(SEL_CAPTCHA_INPUT, captcha_text)

            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS):
                    page.click(SEL_SUBMIT_BTN)
            except PWTimeoutError as e:
                last_message = f"submit nav timeout: {e}"
                continue

            html = page.content()
            result = parser.parse(html)

            if result.status == "CAPTCHA_WRONG":
                last_message = "server says captcha wrong"
                continue

            if result.status == "SUCCESS":
                screenshot_path = self._save_screenshot(page, mst, timestamp)
                return CrawlOutcome(mst, "SUCCESS", result.rows, str(screenshot_path), attempt, None, timestamp, tab)

            if result.status == "NOT_FOUND":
                screenshot_path = self._save_screenshot(page, mst, timestamp)
                return CrawlOutcome(mst, "NOT_FOUND", [], str(screenshot_path), attempt, result.raw_message, timestamp, tab)

            # UNKNOWN: chụp lại để debug rồi return
            screenshot_path = self._save_screenshot(page, mst, timestamp)
            return CrawlOutcome(mst, "UNKNOWN", [], str(screenshot_path), attempt, result.raw_message, timestamp, tab)

        return CrawlOutcome(mst, "ERROR", [], None, self.max_retry, last_message or "max retries exceeded", timestamp, tab)

    def _solve_current_captcha(self, page: Page, mst: str, attempt: int) -> Optional[str]:
        img_bytes = self._download_captcha(page)
        if img_bytes is None:
            return None
        tag = f"{mst}_a{attempt}"
        debug_dir = self.captcha_debug_dir if self.debug else None
        return captcha_solver.solve(img_bytes, debug_dir=debug_dir, tag=tag)

    def _download_captcha(self, page: Page) -> Optional[bytes]:
        """Force-refresh captcha img trên DOM rồi chụp screenshot của nó.

        QUAN TRỌNG: trang gốc dùng URL captcha `?uid=` rỗng → browser cache ảnh
        và KHÔNG refetch giữa các lần reload. Khi đó ảnh hiển thị (cached) khác
        với captcha mà server đã rotate trong session → mọi submit đều fail.

        Cách fix: gán src mới với `?uid=<timestamp>` duy nhất, đợi img load xong,
        rồi mới screenshot. Hành động set src làm browser GET ảnh mới, server
        sinh captcha mới và lưu vào session → ảnh và session sync.
        """
        try:
            self._refresh_captcha(page)
            return page.locator(SEL_CAPTCHA_IMG).first.screenshot()
        except Exception:
            return None

    def _refresh_captcha(self, page: Page) -> None:
        """Force ảnh captcha trên trang lấy uid mới (server sẽ rotate captcha trong session).

        Trả về sau khi img mới đã load xong. Nếu load timeout, vẫn proceed
        (sẽ rely vào retry nếu screenshot không kịp).
        """
        new_uid = int(time.time() * 1000)
        page.evaluate(
            """(newUid) => new Promise((resolve) => {
                const img = document.querySelector('img[src*="captcha.png"]');
                if (!img) { resolve(); return; }
                const base = img.src.split('?')[0];
                let done = false;
                const finish = () => { if (!done) { done = true; resolve(); } };
                img.onload = finish;
                img.onerror = finish;
                img.src = base + '?uid=' + newUid;
                setTimeout(finish, 5000);
            })""",
            new_uid,
        )

    def _save_screenshot(self, page: Page, mst: str, timestamp: str) -> Path:
        filename = f"{mst}_{timestamp}.png"
        path = self.screenshot_dir / filename
        page.screenshot(path=str(path), full_page=True)
        return path
