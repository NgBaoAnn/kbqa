"""Indexing Service — Convert VietMedKG CSV data to text documents for LightRAG.

This module transforms structured CSV medical data into natural-language
document paragraphs suitable for LightRAG's entity/relationship extraction.
Each row in the VietMedKG CSV becomes a self-contained document describing
a single disease with all its associated information.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column mapping: VietMedKG CSV → Document fields ──────────────────────
# Based on docs/13_GRAPH_SCHEMA_DESIGN.md section 2.2
VIETMEDKG_COLUMNS = {
    "tên_bệnh": "disease_name",
    "mô_tả_bệnh": "description",
    "loại_bệnh": "category",
    "nguyên_nhân": "cause",
    "triệu_chứng": "symptoms",
    "kiểm_tra": "check_method",
    "đối_tượng_dễ_mắc_bệnh": "people_easy_get",
    "phương_pháp": "cure_method",
    "khoa_điều_trị": "cure_department",
    "tỉ_lệ_chữa_khỏi": "cure_probability",
    "đề_xuất_thuốc": "drug_recommend",
    "thuốc_phổ_biến": "drug_common",
    "thông_tin_thuốc": "drug_detail",
    "nên_ăn_thực_phẩm_chứa": "nutrition_do_eat",
    "đề_xuất_món_ăn": "nutrition_recommend_meal",
    "không_nên_ăn": "nutrition_not_eat",
    "cách_phòng_tránh": "prevention",
    "bệnh_đi_kèm": "linked_diseases",
}


def _safe_str(value: object) -> str:
    """Convert a value to string, handling NaN/None gracefully."""
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip()


def _row_to_document(row: pd.Series) -> str:
    """Convert a single CSV row into a natural-language document paragraph.

    The output is a Vietnamese text block that LightRAG will parse to
    extract entities and relationships automatically.

    Args:
        row: A pandas Series representing one row of the VietMedKG CSV.

    Returns:
        A formatted text document describing the disease.
    """
    name = _safe_str(row.get("tên_bệnh", ""))
    if not name:
        return ""

    sections = [f"Bệnh: {name}."]

    desc = _safe_str(row.get("mô_tả_bệnh", ""))
    if desc:
        sections.append(f"Mô tả: {desc}")

    category = _safe_str(row.get("loại_bệnh", ""))
    if category:
        sections.append(f"Loại bệnh: {category}.")

    cause = _safe_str(row.get("nguyên_nhân", ""))
    if cause:
        sections.append(f"Nguyên nhân gây bệnh: {cause}")

    symptoms = _safe_str(row.get("triệu_chứng", ""))
    if symptoms:
        sections.append(f"Triệu chứng: {symptoms}")

    check = _safe_str(row.get("kiểm_tra", ""))
    if check:
        sections.append(f"Phương pháp kiểm tra: {check}")

    people = _safe_str(row.get("đối_tượng_dễ_mắc_bệnh", ""))
    if people:
        sections.append(f"Đối tượng dễ mắc bệnh: {people}")

    cure = _safe_str(row.get("phương_pháp", ""))
    if cure:
        sections.append(f"Phương pháp điều trị: {cure}")

    dept = _safe_str(row.get("khoa_điều_trị", ""))
    if dept:
        sections.append(f"Khoa điều trị: {dept}.")

    prob = _safe_str(row.get("tỉ_lệ_chữa_khỏi", ""))
    if prob:
        sections.append(f"Tỉ lệ chữa khỏi: {prob}.")

    drug_rec = _safe_str(row.get("đề_xuất_thuốc", ""))
    if drug_rec:
        sections.append(f"Thuốc đề xuất: {drug_rec}")

    drug_common = _safe_str(row.get("thuốc_phổ_biến", ""))
    if drug_common:
        sections.append(f"Thuốc phổ biến: {drug_common}")

    drug_detail = _safe_str(row.get("thông_tin_thuốc", ""))
    if drug_detail:
        sections.append(f"Thông tin thuốc: {drug_detail}")

    eat = _safe_str(row.get("nên_ăn_thực_phẩm_chứa", ""))
    if eat:
        sections.append(f"Nên ăn: {eat}")

    meal = _safe_str(row.get("đề_xuất_món_ăn", ""))
    if meal:
        sections.append(f"Món ăn đề xuất: {meal}")

    not_eat = _safe_str(row.get("không_nên_ăn", ""))
    if not_eat:
        sections.append(f"Không nên ăn: {not_eat}")

    prevention = _safe_str(row.get("cách_phòng_tránh", ""))
    if prevention:
        sections.append(f"Cách phòng tránh: {prevention}")

    linked = _safe_str(row.get("bệnh_đi_kèm", ""))
    if linked:
        sections.append(f"Bệnh đi kèm: {linked}")

    return "\n".join(sections)


def csv_to_documents(csv_path: str | Path) -> list[str]:
    """Read a VietMedKG CSV file and convert each row to a text document.

    Args:
        csv_path: Path to the VietMedKG data_translated.csv file.

    Returns:
        List of text documents, one per disease.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV has no valid rows.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info("Reading VietMedKG CSV from: %s", csv_path)
    df = pd.read_csv(csv_path, encoding="utf-8")

    logger.info(
        "CSV loaded: %d rows, %d columns. Columns: %s",
        len(df),
        len(df.columns),
        list(df.columns),
    )

    documents: list[str] = []
    skipped = 0

    for _, row in df.iterrows():
        doc = _row_to_document(row)
        if doc:
            documents.append(doc)
        else:
            skipped += 1

    if not documents:
        raise ValueError(f"No valid documents generated from {csv_path}")

    logger.info(
        "Generated %d documents from CSV (%d rows skipped due to missing disease name).",
        len(documents),
        skipped,
    )

    return documents


def get_csv_stats(csv_path: str | Path) -> dict:
    """Get basic statistics about the VietMedKG CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Dict with row count, column count, missing value stats, etc.
    """
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path, encoding="utf-8")

    stats = {
        "file": str(csv_path),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": list(df.columns),
        "missing_values": {
            col: int(df[col].isna().sum())
            for col in df.columns
            if df[col].isna().sum() > 0
        },
        "unique_diseases": int(df.iloc[:, 0].nunique()) if len(df.columns) > 0 else 0,
    }
    return stats
