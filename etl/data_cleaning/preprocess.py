"""
preprocess.py

Cleans the raw dataset by removing brackets, quotes, and resolving list-like strings.
Transforms raw scraped data into a clean, comma-separated format.
Outputs: data/processed/preprocessed_data.csv
"""

import pandas as pd
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
RAW_CSV = BASE_DIR / "raw" / "raw_data.csv"
PROCESSED_CSV = BASE_DIR / "processed" / "preprocessed_data.csv"

def clean_string_lists(val):
    """
    Cleans strings that look like Python lists: "['A', 'B']" -> "A, B"
    Also removes rogue brackets and quotes.
    """
    if pd.isna(val):
        return val
        
    val = str(val).strip()
    
    # Remove all square brackets, single quotes, and double quotes
    val = val.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
    
    # If the value is empty after cleaning, return None (will be dropped or ignored later)
    if not val or val.lower() in ["nan", "none", "không có thông tin"]:
        return None
        
    return val

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Perform data cleaning on the entire dataframe."""
    log.info(f"Original dataset shape: {df.shape}")
    
    # Rename Vietnamese columns to English schema expected by Benchmark tools
    col_rename = {
        "tên_bệnh": "disease_name",
        "mô_tả_bệnh": "disease_description",
        "loại_bệnh": "disease_category",
        "cách_phòng_tránh": "disease_prevention",
        "nguyên_nhân": "disease_cause",
        "triệu_chứng": "disease_symptom",
        "đối_tượng_dễ_mắc_bệnh": "people_easy_get",
        "bệnh_đi_kèm": "associated_disease",
        "phương_pháp": "cure_method",
        "khoa_điều_trị": "cure_department",
        "tỉ_lệ_chữa_khỏi": "cure_probability",
        "kiểm_tra": "check_method",
        "nên_ăn_thực_phẩm_chứa": "nutrition_do_eat",
        "không_nên_ăn_thực_phẩm_chứa": "nutrition_not_eat",
        "đề_xuất_món_ăn": "nutrition_recommend_eat",
        "đề_xuất_thuốc": "drug_recommend",
        "thuốc_phổ_biến": "drug_common",
        "thông_tin_thuốc": "drug_detail"
    }
    df = df.rename(columns=col_rename)
    
    # 1. Drop rows where essential column is missing
    if 'disease_name' in df.columns:
        df = df.dropna(subset=['disease_name'])
            
    # 2. Apply robust string cleaning to ALL columns
    for col in df.columns:
        df[col] = df[col].apply(clean_string_lists)
    
    # 3. Deduplication
    df = df.drop_duplicates()
    
    log.info(f"Dataset shape after cleaning: {df.shape}")
    return df

def run_pipeline():
    if not RAW_CSV.exists():
        log.error(f"Raw data file not found: {RAW_CSV}")
        return
        
    log.info("Loading raw data...")
    df = pd.read_csv(RAW_CSV)
    
    log.info("Cleaning data...")
    df_clean = clean_data(df)
    
    log.info("Saving preprocessed data...")
    PROCESSED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(PROCESSED_CSV, index=False)
    
    log.info(f"Successfully saved clean data to {PROCESSED_CSV}")

if __name__ == "__main__":
    run_pipeline()
