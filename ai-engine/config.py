"""AI Engine configuration — model names, timeouts, API endpoints."""

import os
from dotenv import load_dotenv

load_dotenv()

# LLM Server
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3:8b-instruct-q4_0")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Benchmark models to compare
BENCHMARK_MODELS = [
    "llama3:8b-instruct-q4_0",
    "qwen2.5:7b",
    # "mistral:7b-instruct",  # uncomment if GPU allows
]
