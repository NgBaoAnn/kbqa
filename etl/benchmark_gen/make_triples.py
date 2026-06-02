"""
make_triples.py

Reads the cleaned medical dataset and extracts entity relationships (triples).
Outputs: data/benchmark/triples.json
"""

import pandas as pd
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
INPUT_CSV = BASE_DIR / "processed" / "preprocessed_data.csv"
OUTPUT_JSON = BASE_DIR / "benchmark" / "triples.json"

def create_list_of_dicts(df: pd.DataFrame) -> list:
    result = []
    # Drop rows without a valid disease_name
    if 'disease_name' not in df.columns:
        log.error("The 'disease_name' column is missing from the dataset.")
        return result
        
    df = df.dropna(subset=['disease_name'])
    
    for _, row in df.iterrows():
        disease_name = str(row['disease_name']).strip()
        
        for col in df.columns:
            if col == 'disease_name':
                continue
                
            val = str(row[col]).strip()
            
            # Note: We don't need to replace brackets here anymore because
            # data_cleaning/preprocess.py already did all the heavy lifting!
            
            if pd.isna(row[col]) or val.lower() in ["", "nan", "none", "không có thông tin"]:
                continue
                
            result.append({
                "header": disease_name,
                "relation": col,
                "tail": val
            })
            
    return result

def generate_triples():
    if not INPUT_CSV.exists():
        log.error(f"Input file not found: {INPUT_CSV}")
        return
        
    log.info(f"Loading data from {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    log.info("Extracting triples...")
    triples = create_list_of_dicts(df)
    
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(triples, f, ensure_ascii=False, indent=4)
        
    log.info(f"Successfully saved {len(triples)} triples to {OUTPUT_JSON}")

if __name__ == "__main__":
    generate_triples()
