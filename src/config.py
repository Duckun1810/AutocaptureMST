"""Cấu hình chung cho tool tra cứu MST."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL_TNCN = "https://tracuunnt.gdt.gov.vn/tcnnt/mstcn.jsp"  # Cá nhân
BASE_URL_DN = "https://tracuunnt.gdt.gov.vn/tcnnt/mstdn.jsp"   # Doanh nghiệp


def resolve_url(mst: str) -> str:
    """MST 10 chữ số → tab DN, ngược lại → tab TNCN."""
    digits = "".join(c for c in mst if c.isdigit())
    return BASE_URL_DN if len(digits) == 10 else BASE_URL_TNCN


SEL_MST_INPUT = 'input[name="mst"]'
SEL_CAPTCHA_INPUT = '#captcha'
SEL_CAPTCHA_IMG = 'img[src*="captcha.png"]'
SEL_SUBMIT_BTN = 'input.subBtn'
SEL_RESULT_TABLE = 'table.ta_border'

CAPTCHA_LENGTH = 5
CAPTCHA_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"

MAX_CAPTCHA_RETRY = 5
NAV_TIMEOUT_MS = 30000
DELAY_MIN_SEC = 1.0
DELAY_MAX_SEC = 3.0

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT_DIR / "input" / "mst_list.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
SCREENSHOT_SUBDIR = "screenshots"
CAPTCHA_DEBUG_SUBDIR = "captcha_debug"
RESULTS_CSV_NAME = "results.csv"
ERRORS_LOG_NAME = "errors.log"

CAPTCHA_ERROR_KEYWORDS = [
    "vui lòng nhập đúng mã xác nhận",
    "nhập đúng mã xác nhận",
    "mã xác nhận không đúng",
    "mã xác nhận sai",
    "không đúng mã",
]
NOT_FOUND_KEYWORDS = ["không tìm thấy", "không có dữ liệu", "không tồn tại"]

# === LLM (Alibaba Qwen via DashScope, OpenAI-compatible) ===
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
DASHSCOPE_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-vl-max-latest")
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "30"))
