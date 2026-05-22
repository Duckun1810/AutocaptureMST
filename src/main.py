"""CLI entry point cho tool tra cứu MST."""
from __future__ import annotations

import argparse
import csv
import logging
import random
import sys
import time
from pathlib import Path
from typing import List

from src.config import (
    DEFAULT_INPUT,
    DEFAULT_OUTPUT_DIR,
    DELAY_MAX_SEC,
    DELAY_MIN_SEC,
    ERRORS_LOG_NAME,
    MAX_CAPTCHA_RETRY,
    RESULTS_CSV_NAME,
)
from src.crawler import CrawlOutcome, MSTCrawler


RESULT_FIELDS = [
    "mst",
    "tab",
    "status",
    "ten_nnt",
    "co_quan_thue",
    "trang_thai",
    "screenshot_path",
    "retry_count",
    "message",
    "timestamp",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tra cứu MST tự động từ trang tracuunnt.gdt.gov.vn")
    p.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT, help="File CSV/TXT chứa danh sách MST (mỗi dòng 1 MST hoặc cột 'mst')")
    p.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT_DIR, help="Thư mục output")
    p.add_argument("--debug", action="store_true", help="Bật visible browser + lưu ảnh captcha debug")
    p.add_argument("--max-retry", type=int, default=MAX_CAPTCHA_RETRY, help="Số lần retry tối đa khi captcha sai")
    p.add_argument("--delay", type=str, default=f"{DELAY_MIN_SEC},{DELAY_MAX_SEC}", help="Delay random giữa các MST, format 'min,max' (giây)")
    return p.parse_args()


def read_msts(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    msts: List[str] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        if "," in sample or "\t" in sample or path.suffix.lower() == ".csv":
            reader = csv.DictReader(f)
            if reader.fieldnames and any(fn.strip().lower() == "mst" for fn in reader.fieldnames):
                key = next(fn for fn in reader.fieldnames if fn.strip().lower() == "mst")
                for row in reader:
                    val = (row.get(key) or "").strip()
                    if val:
                        msts.append(val)
            else:
                f.seek(0)
                for line in f:
                    val = line.split(",")[0].strip()
                    if val and val.lower() != "mst":
                        msts.append(val)
        else:
            for line in f:
                val = line.strip()
                if val:
                    msts.append(val)
    return msts


def parse_delay(spec: str) -> tuple[float, float]:
    try:
        lo, hi = spec.split(",")
        return float(lo), float(hi)
    except Exception as e:
        raise SystemExit(f"Invalid --delay '{spec}', expected 'min,max': {e}")


def outcome_to_row(outcome: CrawlOutcome) -> dict:
    base = {f: "" for f in RESULT_FIELDS}
    base.update({
        "mst": outcome.mst,
        "tab": outcome.tab,
        "status": outcome.status,
        "screenshot_path": outcome.screenshot_path or "",
        "retry_count": outcome.retry_count,
        "message": outcome.message or "",
        "timestamp": outcome.timestamp,
    })
    if outcome.rows:
        first = outcome.rows[0]
        for k in ("ten_nnt", "co_quan_thue", "trang_thai"):
            if k in first:
                base[k] = first[k]
    return base


def main() -> int:
    args = parse_args()
    delay_min, delay_max = parse_delay(args.delay)
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / ERRORS_LOG_NAME
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    log = logging.getLogger("mst")

    try:
        msts = read_msts(args.input)
    except FileNotFoundError as e:
        log.error(str(e))
        return 2

    if not msts:
        log.warning("Danh sách MST rỗng — không có gì để xử lý.")
        return 0

    log.info("Tổng số MST cần tra: %d", len(msts))

    results_path = output_dir / RESULTS_CSV_NAME
    is_new_file = not results_path.exists()

    with open(results_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if is_new_file:
            writer.writeheader()

        with MSTCrawler(output_dir=output_dir, debug=args.debug, max_retry=args.max_retry) as crawler:
            for idx, mst in enumerate(msts, start=1):
                log.info("[%d/%d] Tra MST: %s (tab: %s)", idx, len(msts), mst, "DN" if len("".join(c for c in mst if c.isdigit())) == 10 else "TNCN")
                try:
                    outcome = crawler.lookup(mst)
                except Exception as e:
                    log.exception("Exception khi tra MST %s: %s", mst, e)
                    outcome = CrawlOutcome(mst=mst, status="ERROR", rows=[], screenshot_path=None,
                                            retry_count=0, message=f"exception: {e}",
                                            timestamp="", tab="")
                writer.writerow(outcome_to_row(outcome))
                f.flush()
                log.info("  → status=%s retry=%d msg=%s", outcome.status, outcome.retry_count, outcome.message or "")

                if idx < len(msts):
                    sleep_for = random.uniform(delay_min, delay_max)
                    time.sleep(sleep_for)

    log.info("Hoàn tất. Kết quả: %s", results_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
