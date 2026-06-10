# Hướng dẫn chạy Ingestion trên Kaggle

## Tổng quan

Notebook [`ingest_qdrant.ipynb`](./ingest_qdrant.ipynb) thực hiện:

```
preprocessed_data.csv (8806 bệnh)
    ↓ sentence-transformers BAAI/bge-m3 (GPU T4)
    ↓ ~5-10 phút (GPU) / ~30-40 phút (CPU)
    ↓ upsert trực tiếp → Qdrant Cloud
         collection: lightrag_vdb_chunks
```

**Không cần Ollama. Không cần LLM.**

---

## Bước 1 — Upload CSV lên Kaggle

1. Vào [kaggle.com/datasets](https://www.kaggle.com/datasets)
2. Chọn **New Dataset** → đặt tên `vietmedkg`
3. Upload file `data/preprocessed_data.csv` từ project
4. Đặt **Visibility = Private**
5. Nhấn **Create**

> Sau khi tạo xong, đường dẫn trên Kaggle sẽ là `/kaggle/input/vietmedkg/preprocessed_data.csv`

---

## Bước 2 — Tạo Notebook mới trên Kaggle

1. Vào [kaggle.com/code](https://www.kaggle.com/code)
2. Chọn **New Notebook**
3. Trong notebook vừa tạo:
   - **File** → **Import Notebook** → upload file `notebooks/ingest_qdrant.ipynb`
   - Hoặc copy-paste từng cell thủ công

---

## Bước 3 — Thêm Dataset vào Notebook

Trong cửa sổ notebook Kaggle:
1. Bên phải → **Add data** → **Your Datasets**
2. Tìm dataset `vietmedkg` vừa tạo → nhấn **+**
3. Xác nhận đường dẫn là `/kaggle/input/vietmedkg/preprocessed_data.csv`

---

## Bước 4 — Đặt Qdrant Credentials (Kaggle Secrets)

>  **Không** hardcode API key trực tiếp trong notebook (đặc biệt nếu notebook public)

1. Bên trái notebook → **Add-ons** → **Secrets**
2. Thêm 2 secret:

| Name | Value |
|------|-------|
| `QDRANT_URL` | `https://dacb4228-6c2b-438f-98c7-3378b52d5b05.eu-west-2-0.aws.cloud.qdrant.io` |
| `QDRANT_API_KEY` | *(lấy từ file `.env` trong project)* |

3. Bật toggle **Allow notebook to access** cho cả hai

---

## Bước 5 — Bật GPU

1. Bên phải notebook → **Settings** → **Accelerator**
2. Chọn **GPU T4 x1** (miễn phí, tới 30h/tuần)

---

## Bước 6 — Chạy notebook

Nhấn **Run All** hoặc chạy từng cell theo thứ tự:

| Cell | Mô tả | Thời gian ước tính |
|------|-------|-------------------|
| Cell 1 | Cài `qdrant-client`, `sentence-transformers`, `pandas` | ~1 phút |
| Cell 2 | Load credentials + cấu hình | Tức thì |
| Cell 3 | Đọc CSV, tạo 8806 đoạn văn | ~5 giây |
| Cell 4 | Định nghĩa hàm tạo ID | Tức thì |
| Cell 5 | Download + load BAAI/bge-m3 | ~2-3 phút (lần đầu) |
| Cell 6 | Kết nối Qdrant, tạo collection nếu cần | ~5 giây |
| **Cell 7** | **Embed + Upsert 8806 chunks** | **~5-10 phút (GPU)** |
| Cell 8 | Verify + test search | ~5 giây |

---

## Bước 7 — Xác nhận thành công

Sau khi chạy xong, Cell 8 sẽ hiển thị:

```
 Final count in Qdrant: 8,806 chunks
 Expected:              8,806 chunks
 INGESTION COMPLETE! Tất cả chunks đã được nạp vào Qdrant.

--- Test semantic search ---
Query: 'bệnh sốt xuất huyết triệu chứng'
Top 3 results:
  Score=0.872 | Disease=Sốt xuất huyết Dengue
  Score=0.761 | Disease=Sốt xuất huyết
  Score=0.734 | Disease=Bệnh sốt rét
```

---

## Lưu ý kỹ thuật quan trọng

### Tại sao không dùng Ollama trên Kaggle?
Kaggle không hỗ trợ chạy Ollama. Thay vào đó, notebook dùng `sentence-transformers` để load model `BAAI/bge-m3` **trực tiếp từ HuggingFace** — đây là **cùng một model** với cái Ollama đang dùng cục bộ, nên vector dimension vẫn là **1024-dim**.

### Format Qdrant — khớp với LightRAG
Mỗi điểm được insert với payload:
```json
{
  "id":           "<md5-hash-of-text>",
  "workspace_id": "_",
  "created_at":   1234567890,
  "content":      "<đoạn văn mô tả bệnh>",
  "full_doc_id":  "<tên bệnh>",
  "file_path":    "preprocessed_data.csv"
}
```
Đây là **chính xác format** mà `lightrag_service.py` đọc khi query `naive` mode.

### Resume nếu bị ngắt
Cell 7 dùng `upsert` (không phải `insert`), nên nếu bị ngắt giữa chừng, chạy lại Cell 7 sẽ **tự động bỏ qua** các chunk đã có (overwrite an toàn, không duplicate).

---

## Sau khi Ingestion hoàn thành

Quay về máy local, khởi động backend:
```bash
cd /Users/nguyenbaoan/codeLab/kbqa
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

Test thử với câu hỏi mơ hồ:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "tôi hay bị đau đầu và sốt thì có thể bị bệnh gì"}'
```

---

#  Hướng dẫn chạy Benchmark trên Kaggle

## Mục đích

Notebook [`run_benchmark.ipynb`](./run_benchmark.ipynb) chạy toàn bộ **45 câu benchmark mù** với model lớn hơn (qwen2.5:7b / 14b) để so sánh với kết quả local (qwen2.5:3b).

## Kiến trúc trên Kaggle

```
Kaggle Notebook (GPU T4 x1)
  ├── Ollama server    ← pull & serve qwen2.5:7b hoặc 14b
  ├── FastAPI backend  ← kết nối Neo4j AuraDB (cloud)
  └── Benchmark script ← gọi API, chấm điểm 45 câu
```

## Bước 1 — Chuẩn bị Kaggle Secrets

Vào notebook → **Add-ons** → **Secrets**, thêm các secret sau và bật toggle **Allow notebook to access**:

| Name | Value |
|------|-------|
| `NEO4J_URI` | `neo4j+s://xxxxxxxx.databases.neo4j.io` |
| `NEO4J_USERNAME` | `neo4j` |
| `NEO4J_PASSWORD` | *(từ .env local)* |
| `QDRANT_URL` | `https://dacb4228-...cloud.qdrant.io` |
| `QDRANT_API_KEY` | *(từ .env local)* |

## Bước 2 — Upload và cài đặt

1. Vào [kaggle.com/code](https://www.kaggle.com/code) → **New Notebook**
2. **File** → **Import Notebook** → upload `notebooks/run_benchmark.ipynb`
3. **Settings** → **Accelerator** → **GPU T4 x1**
4. **Settings** → **Internet** → **On**

## Bước 3 — Chọn model và chạy

Trong Cell 2, đổi `MODEL_NAME`:

```python
MODEL_NAME = "qwen2.5:7b"   # hoặc "qwen2.5:14b"
```

Nhấn **Run All**. Tiến trình ước tính:

| Cell | Mô tả | Thời gian |
|------|-------|-----------|
| Cell 1-4 | Kiểm tra môi trường, clone repo, cài packages | ~3 phút |
| Cell 5-6 | Cài Ollama + pull LLM model | ~5-15 phút |
| Cell 7-9 | Cài embedding model + khởi động backend | ~3 phút |
| Cell 10 | Smoke test 1 câu | ~30s |
| **Cell 11** | **Benchmark 45 câu** | **~15-40 phút** |
| Cell 12-13 | Hiển thị + so sánh kết quả | ~5s |

## Bước 4 — Tải kết quả

File `benchmark_qwen2.5_7b_YYYYMMDD.md` sẽ xuất hiện ở **Output panel** bên phải → tải về để so sánh với kết quả local.

## Lưu ý

- **Repo phải public** để notebook clone được. Nếu private, thêm `GITHUB_TOKEN` vào Secrets.
- **Qdrant**: Nếu không có cloud data, LightRAG path không hoạt động, nhưng cypher path (phần lớn câu hỏi) vẫn chạy tốt qua Neo4j AuraDB.
- **Giới hạn 12 giờ/session** của Kaggle — benchmark 45 câu thường xong trong 40 phút, rất an toàn.
