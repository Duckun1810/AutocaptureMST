# AutocaptureMST

Tool tự động tra cứu thông tin người nộp thuế TNCN từ trang [tracuunnt.gdt.gov.vn](https://tracuunnt.gdt.gov.vn/tcnnt/mstcn.jsp).

Nhận input là danh sách MST → tự động điền form, OCR captcha, click Tra cứu, screenshot kết quả và xuất CSV.

## Yêu cầu hệ thống
- Windows / macOS / Linux
- **Python 3.10+**
- **API key Alibaba DashScope** (Qwen) — lấy tại https://dashscope-intl.console.aliyun.com/apiKey

OCR engine dùng **Qwen-VL (LLM của Alibaba)** qua DashScope OpenAI-compatible endpoint.

## Cài đặt

```powershell
# 1. Tạo virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Cài Python deps
pip install -r requirements.txt

# 3. Cài Chromium cho Playwright
python -m playwright install chromium

# 4. Setup API key: copy .env.example thành .env rồi điền key
Copy-Item .env.example .env
# Mở file .env, điền DASHSCOPE_API_KEY=sk-...
```

`.env` file gồm 3 biến:
| Biến | Mặc định | Mô tả |
|---|---|---|
| `DASHSCOPE_API_KEY` | (bắt buộc) | API key của Alibaba DashScope |
| `DASHSCOPE_BASE_URL` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Endpoint. Mainland China dùng `dashscope.aliyuncs.com/...` |
| `DASHSCOPE_MODEL` | `qwen-vl-max-latest` | Có thể đổi sang `qwen-vl-plus` (rẻ hơn) hoặc `qwen-vl-ocr-latest` (chuyên OCR) |

## Cách dùng

### Chuẩn bị input
File `input/mst_list.csv` (mỗi dòng 1 MST, có thể có header `mst`):
```csv
mst
0123456789
0987654321
```

Hoặc file `.txt` mỗi dòng 1 MST.

### Chạy
```powershell
python -m src.main --input input/mst_list.csv --output output/
```

Tham số:
| Flag | Mặc định | Mô tả |
|---|---|---|
| `--input`, `-i` | `input/mst_list.csv` | File CSV/TXT chứa danh sách MST |
| `--output`, `-o` | `output/` | Thư mục output |
| `--debug` | off | Hiện browser + lưu ảnh captcha debug |
| `--max-retry` | 5 | Số lần retry tối đa khi captcha OCR/sai |
| `--delay` | `1,3` | Delay random giữa các MST (giây), format `min,max` |

### Output
```
output/
├── screenshots/<mst>_<timestamp>.png   # Screenshot kết quả
├── captcha_debug/<mst>_aN_*.png        # Ảnh captcha gốc + processed (chỉ khi --debug)
├── results.csv                          # Bảng tổng hợp
└── errors.log                           # Log chi tiết
```

Schema `results.csv`:
| Cột | Mô tả |
|---|---|
| mst | Mã số thuế đã tra |
| tab | `DN` (doanh nghiệp) hoặc `TNCN` (cá nhân) — auto-detect theo độ dài MST |
| status | SUCCESS / NOT_FOUND / CAPTCHA_WRONG / UNKNOWN / ERROR |
| ten_nnt | Tên người nộp thuế |
| co_quan_thue | Cơ quan thuế quản lý |
| trang_thai | Trạng thái MST (vd: "NNT đang hoạt động") |
| screenshot_path | Đường dẫn file PNG kết quả |
| retry_count | Số lần thử OCR captcha (1 = thành công ngay lần đầu) |
| message | Thông báo lỗi (nếu có) |
| timestamp | Thời điểm tra cứu |

## Auto-routing 2 tab

Trang gốc có 2 tab tra cứu:
- **Tab "Thông tin về người nộp thuế"** (`mstdn.jsp`) — cho MST doanh nghiệp (**10 chữ số**)
- **Tab "Thông tin về người nộp thuế TNCN"** (`mstcn.jsp`) — cho MST cá nhân (**12–13 chữ số**)

Tool tự động chọn tab phù hợp dựa vào độ dài MST input. Bạn có thể trộn MST DN và MST cá nhân trong cùng 1 file input, tool sẽ tự route từng MST đúng tab.

## Cấu trúc dự án
```
src/
├── main.py            # CLI entry point
├── crawler.py         # Logic Playwright
├── captcha_solver.py  # OCR Tesseract + preprocess
├── parser.py          # Bóc HTML kết quả
└── config.py          # Selectors, URLs, constants
```

## Ghi chú kỹ thuật
- OCR dùng **Qwen-VL** (LLM của Alibaba) qua DashScope OpenAI-compatible endpoint → dùng được `openai` SDK chuẩn.
- Captcha (PNG RGBA) được **flatten về RGB nền trắng** trước khi gửi LLM để tăng độ chắc chắn.
- Captcha được **chụp screenshot từ `<img>` trên DOM** (không fetch lại qua HTTP) để tránh server sinh captcha mới khác với captcha browser đang dùng.
- Local validation: chỉ submit captcha nếu đúng 5 ký tự `[a-z0-9]` → tiết kiệm request lên server.
- Mỗi captcha tốn 1 API call. Captcha trang này khá đơn giản nên dự kiến rất ít khi cần retry.

## Chi phí ước tính
| Model | Giá input/1K tokens | 1 ảnh captcha ~ |
|---|---|---|
| `qwen-vl-max-latest` | $0.0024 | ~$0.002–0.005/lần |
| `qwen-vl-plus` | $0.0008 | ~$0.001–0.002/lần |
| `qwen-vl-ocr-latest` | $0.0012 | ~$0.001–0.003/lần |

(Giá có thể thay đổi, xem trang giá Alibaba để cập nhật)

## Troubleshooting
- **`RuntimeError: DASHSCOPE_API_KEY chưa được set`**: chưa có `.env` hoặc chưa điền key. Xem mục cài đặt.
- **`openai.APIConnectionError`**: kiểm tra kết nối internet và `DASHSCOPE_BASE_URL` (mainland vs international).
- **`playwright._impl._errors.Error: Executable doesn't exist`**: chạy lại `python -m playwright install chromium`.
- **Captcha OCR luôn sai**: bật `--debug`, xem ảnh + response text trong `output/captcha_debug/`. File `*_response.txt` cho biết LLM trả về gì.
