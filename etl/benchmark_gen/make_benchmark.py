"""
make_benchmark.py

Generates the Golden Test Set for evaluating the LLM's Cypher generation capabilities.
Randomly samples 50 questions from 1-hop and 50 questions from 2-hop benchmark datasets
to create a comprehensive and balanced evaluation set.
"""

import json
import random
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SOURCE_1HOP = BASE_DIR / "benchmark" / "1hop.json"
SOURCE_2HOP = BASE_DIR / "benchmark" / "2hop.json"
TARGET_JSON = BASE_DIR / "benchmark" / "golden_test.json"
SAMPLE_SIZE_PER_TYPE = 50

def load_and_sample(file_path: Path, sample_size: int, hop_type: str) -> list:
    if not file_path.exists():
        log.error(f"Source benchmark file not found: {file_path}")
        return []
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.error(f"Failed to read JSON file {file_path}: {e}")
        return []
        
    if not isinstance(data, list):
        log.error(f"Invalid JSON format in {file_path}. Expected a list of dictionaries.")
        return []
        
    log.info(f"Loaded {len(data)} questions from {hop_type} source.")
    
    # Add a metadata tag so we know the difficulty level during evaluation
    for item in data:
        item["complexity"] = hop_type
        
    random.seed(42) # Set seed for reproducibility
    sampled_data = random.sample(data, min(sample_size, len(data)))
    log.info(f"Sampled {len(sampled_data)} questions from {hop_type}.")
    
    return sampled_data

def generate_golden_test_set():
    log.info("Generating balanced Golden Test Set...")
    
    # Sample from both files
    hop1_samples = load_and_sample(SOURCE_1HOP, SAMPLE_SIZE_PER_TYPE, "1-hop")
    hop2_samples = load_and_sample(SOURCE_2HOP, SAMPLE_SIZE_PER_TYPE, "2-hop")
    
    # Combine the samples
    combined_samples = hop1_samples + hop2_samples
    
    if not combined_samples:
        log.error("No data was sampled. Aborting.")
        return
        
    # Shuffle the combined list so 1-hop and 2-hop questions are mixed
    random.seed(42)
    random.shuffle(combined_samples)
    
    # Save to target benchmark directory
    TARGET_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGET_JSON, "w", encoding="utf-8") as f:
        json.dump(combined_samples, f, ensure_ascii=False, indent=4)
        
    log.info(f"Successfully saved {len(combined_samples)} mixed questions to Golden Test Set: {TARGET_JSON}")

if __name__ == "__main__":
    generate_golden_test_set()
