# 11. HẠ TẦNG PHÁT TRIỂN — AegisHealth KBQA

> **Development Infrastructure: Cấu trúc Dự án, Dependencies, và Quy ước**

---

## 1. Cấu trúc Thư mục Dự án (Monorepo)

```
aegishealth-kbqa/
│
├── docs/                           # Tài liệu thiết kế (bộ tài liệu hiện tại)
│   ├── 01_PROJECT_OVERVIEW.md
│   ├── 02_SYSTEM_ARCHITECTURE.md
│   ├── ...
│   └── GAP_ANALYSIS_REPORT.md
│
├── data/                           # Dữ liệu & ETL
│   ├── raw/                        # Dữ liệu gốc chưa xử lý
│   │   ├── symptom2disease.csv
│   │   └── medicine_recommendation.csv
│   ├── processed/                  # Dữ liệu đã transform
│   │   ├── diseases.csv
│   │   ├── symptoms.csv
│   │   ├── drugs.csv
│   │   ├── disease_symptom.csv
│   │   └── disease_drug.csv
│   └── scripts/                    # ETL scripts
│       ├── etl_pipeline.py
│       └── load_to_neo4j.py
│
├── backend/                        # FastAPI Backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Environment configuration
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── query.py            # /api/v1/query endpoint
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── llm_service.py      # LLM interaction (Ollama/vLLM)
│   │   │   ├── graph_service.py    # Neo4j AuraDB connection
│   │   │   └── pipeline.py         # Agent orchestrator
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── request.py          # Pydantic request models
│   │   │   └── response.py         # Pydantic response models
│   │   ├── prompts/
│   │   │   ├── text_to_cypher.txt  # System prompt — Step 1
│   │   │   └── data_to_text.txt    # System prompt — Step 3
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── cypher_validator.py # Cypher syntax checker
│   │       └── sanitizer.py       # Input/Cypher sanitization
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_query.py
│   │   ├── test_llm_service.py
│   │   └── golden_test_set.json    # Benchmark test data
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── web-client/                     # ReactJS Web Application
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface/
│   │   │   ├── renderers/
│   │   │   └── common/
│   │   ├── services/
│   │   │   └── apiService.js
│   │   ├── App.jsx
│   │   └── index.js
│   ├── package.json
│   └── Dockerfile
│
├── mobile-client/                  # Flutter Mobile Application
│   ├── lib/
│   │   ├── screens/
│   │   ├── widgets/
│   │   ├── models/
│   │   ├── services/
│   │   └── main.dart
│   └── pubspec.yaml
│
├── .github/                        # GitHub configurations
│   └── workflows/
│       └── ci.yml                  # CI pipeline (lint + test)
│
├── .gitignore
├── .env.example                    # Template biến môi trường
├── docker-compose.yml              # Orchestrate backend + web
├── README.md                       # Hướng dẫn nhanh
└── LICENSE
```

---

## 2. Quản lý Dependencies

### 2.1. Backend (Python)

**`backend/requirements.txt`**:

```
# == Core Framework ==
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0

# == Database ==
neo4j>=5.15.0

# == AI/LLM ==
openai>=1.10.0          # OpenAI-compatible client (for Ollama/vLLM)
httpx>=0.26.0           # Async HTTP client

# == Data Processing ==
pandas>=2.1.0

# == Utilities ==
python-dotenv>=1.0.0
python-multipart>=0.0.6

# == Testing ==
pytest>=7.4.0
pytest-asyncio>=0.23.0

# == Linting ==
ruff>=0.2.0
```

### 2.2. Web Client (JavaScript)

**`web-client/package.json`** (dependencies chính):

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-bootstrap": "^2.10.0",
    "bootstrap": "^5.3.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "vite": "^5.0.0"
  }
}
```

### 2.3. Mobile Client (Dart/Flutter)

**`mobile-client/pubspec.yaml`** (dependencies chính):

```yaml
dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0
  provider: ^6.1.0
```

---

## 3. Biến Môi trường (Environment Variables)

**`.env.example`**:

```bash
# == Neo4j AuraDB ==
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<password>

# == LLM Server ==
LLM_BASE_URL=http://localhost:11434/v1   # Ollama default
LLM_MODEL_NAME=llama3:8b-instruct-q4_0
LLM_TIMEOUT_SECONDS=30

# == API Configuration ==
API_HOST=0.0.0.0
API_PORT=8000
API_CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# == Logging ==
LOG_LEVEL=INFO
```

> **Quan trọng**: File `.env` chứa credentials thực KHÔNG BAO GIỜ được commit lên Git. Chỉ commit `.env.example` (template).

---

## 4. Containerization (Docker)

### 4.1. Backend Dockerfile (Giản lược)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.2. Docker Compose (Backend + Web)

```yaml
version: "3.8"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: ./backend/.env
    depends_on: []    # Neo4j AuraDB là cloud, không cần local service

  web:
    build: ./web-client
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://backend:8000/api/v1
```

> **Lưu ý**: Neo4j AuraDB chạy trên cloud → không cần container Neo4j local. LLM server (Ollama) chạy trên máy host, expose port cho container backend.

---

## 5. CI/CD Pipeline (GitHub Actions)

### 5.1. Cấu hình CI cơ bản

**`.github/workflows/ci.yml`**:

```yaml
name: CI Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt

      - name: Lint with Ruff
        run: |
          cd backend
          ruff check app/

      - name: Run tests
        run: |
          cd backend
          pytest tests/ -v
        env:
          NEO4J_URI: ${{ secrets.NEO4J_URI }}
          NEO4J_USERNAME: ${{ secrets.NEO4J_USERNAME }}
          NEO4J_PASSWORD: ${{ secrets.NEO4J_PASSWORD }}
```

---

## 6. Quy ước Code (Coding Conventions)

### 6.1. Python (Backend)

| Quy ước | Công cụ |
|---|---|
| **Style guide** | PEP 8 |
| **Linter** | Ruff |
| **Type hints** | Bắt buộc cho mọi function signature |
| **Docstrings** | Google style cho mọi public function/class |
| **Naming** | `snake_case` cho functions/variables, `PascalCase` cho classes |

### 6.2. JavaScript (Web Client)

| Quy ước | Công cụ |
|---|---|
| **Style guide** | Airbnb JavaScript Style |
| **Linter** | ESLint |
| **Components** | Functional components + Hooks (không dùng class components) |
| **Naming** | `PascalCase` cho Components, `camelCase` cho functions/variables |

### 6.3. Dart (Mobile Client)

| Quy ước | Công cụ |
|---|---|
| **Style guide** | Effective Dart |
| **Linter** | `flutter analyze` |
| **State management** | Provider pattern |
