"""
import_vietmedkg.py — Import VietMedKG data into Neo4j AuraDB

Schema (based on VietMedKG paper, ACM TALLIP 2025):
  Node Labels: Disease, Symptom, Treatment, Medicine, Advice
  Relationships: HAS_SYMPTOM, HAS_TREATMENT, IS_PRESCRIBED, HAS_ADVICE, IS_LINKED_WITH

Usage:
  1. Create .env file with NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD
  2. python import_vietmedkg.py [--dry-run] [--batch-size 500]

Adapted from: https://github.com/HySonLab/VietMedKG/blob/main/preprocessing/kgraph/create_KG.py
"""

import os
import sys
import csv
import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# ─── Config ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Path to data
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vietmedkg" / "data"
CSV_FILE = DATA_DIR / "data_translated.csv"

# CSV column name → schema mapping
# CSV columns (Vietnamese): tên_bệnh, mô_tả_bệnh, loại_bệnh, nguyên_nhân, ...
# Graph properties (English): disease_name, disease_description, disease_category, ...

COL_MAP = {
    # Disease node
    "tên_bệnh": "disease_name",
    "mô_tả_bệnh": "disease_description",
    "loại_bệnh": "disease_category",
    "nguyên_nhân": "disease_cause",
    # Symptom node
    "triệu_chứng": "disease_symptom",
    "kiểm_tra": "check_method",
    "đối_tượng_dễ_mắc_bệnh": "people_easy_get",
    # Treatment node
    "phương_pháp": "cure_method",
    "khoa_điều_trị": "cure_department",
    "tỉ_lệ_chữa_khỏi": "cure_probability",
    # Medicine node
    "đề_xuất_thuốc": "drug_recommend",
    "thuốc_phổ_biến": "drug_common",
    "thông_tin_thuốc": "drug_detail",
    # Advice node
    "nên_ăn_thực_phẩm_chứa": "nutrition_do_eat",
    "không_nên_ăn_thực_phẩm_chứa": "nutrition_not_eat",
    "đề_xuất_món_ăn": "nutrition_recommend_meal",
    "cách_phòng_tránh": "disease_prevention",
    # Associated disease
    "bệnh_đi_kèm": "associated_disease",
}


# ─── Neo4j Queries ───────────────────────────────────────────────────────────

CONSTRAINTS_QUERIES = [
    "CREATE CONSTRAINT disease_name_unique IF NOT EXISTS FOR (d:Disease) REQUIRE d.disease_name IS UNIQUE",
    "CREATE CONSTRAINT symptom_key_unique IF NOT EXISTS FOR (s:Symptom) REQUIRE s.disease_name IS UNIQUE",
    "CREATE CONSTRAINT treatment_key_unique IF NOT EXISTS FOR (t:Treatment) REQUIRE t.disease_name IS UNIQUE",
    "CREATE CONSTRAINT medicine_key_unique IF NOT EXISTS FOR (m:Medicine) REQUIRE m.disease_name IS UNIQUE",
    "CREATE CONSTRAINT advice_key_unique IF NOT EXISTS FOR (a:Advice) REQUIRE a.disease_name IS UNIQUE",
]

# Batch import queries using UNWIND for performance
IMPORT_DISEASE_QUERY = """
UNWIND $rows AS row
MERGE (d:Disease {disease_name: row.disease_name})
SET d.disease_description = row.disease_description,
    d.disease_category = row.disease_category,
    d.disease_cause = row.disease_cause
"""

IMPORT_SYMPTOM_QUERY = """
UNWIND $rows AS row
WITH row
WHERE row.disease_symptom IS NOT NULL AND row.disease_symptom <> ''
    AND row.disease_symptom <> 'Không có thông tin'
MERGE (s:Symptom {disease_name: row.disease_name})
SET s.disease_symptom = row.disease_symptom,
    s.check_method = row.check_method,
    s.people_easy_get = row.people_easy_get
WITH s, row
MATCH (d:Disease {disease_name: row.disease_name})
MERGE (d)-[:HAS_SYMPTOM]->(s)
"""

IMPORT_TREATMENT_QUERY = """
UNWIND $rows AS row
WITH row
WHERE row.cure_method IS NOT NULL AND row.cure_method <> ''
    AND row.cure_method <> 'Không có thông tin'
MERGE (t:Treatment {disease_name: row.disease_name})
SET t.cure_method = row.cure_method,
    t.cure_department = row.cure_department,
    t.cure_probability = row.cure_probability
WITH t, row
MATCH (d:Disease {disease_name: row.disease_name})
MERGE (d)-[:HAS_TREATMENT]->(t)
"""

IMPORT_MEDICINE_QUERY = """
UNWIND $rows AS row
WITH row
WHERE row.drug_common IS NOT NULL AND row.drug_common <> ''
    AND row.drug_common <> 'Không có thông tin'
MERGE (m:Medicine {disease_name: row.disease_name})
SET m.drug_detail = row.drug_detail,
    m.drug_common = row.drug_common,
    m.drug_recommend = row.drug_recommend
WITH m, row
MATCH (d:Disease {disease_name: row.disease_name})
MERGE (d)-[:IS_PRESCRIBED]->(m)
"""

IMPORT_ADVICE_QUERY = """
UNWIND $rows AS row
WITH row
WHERE (row.nutrition_do_eat IS NOT NULL AND row.nutrition_do_eat <> ''
    AND row.nutrition_do_eat <> 'Không có thông tin')
    OR (row.disease_prevention IS NOT NULL AND row.disease_prevention <> ''
    AND row.disease_prevention <> 'Không có thông tin')
MERGE (a:Advice {disease_name: row.disease_name})
SET a.nutrition_do_eat = row.nutrition_do_eat,
    a.nutrition_recommend_meal = row.nutrition_recommend_meal,
    a.nutrition_not_eat = row.nutrition_not_eat,
    a.disease_prevention = row.disease_prevention
WITH a, row
MATCH (d:Disease {disease_name: row.disease_name})
MERGE (d)-[:HAS_ADVICE]->(a)
"""

IMPORT_LINKED_QUERY = """
UNWIND $rows AS row
WITH row
WHERE row.associated_disease IS NOT NULL AND row.associated_disease <> ''
    AND row.associated_disease <> 'Không có thông tin'
MATCH (d1:Disease {disease_name: row.disease_name})
MATCH (d2:Disease {disease_name: row.associated_disease})
MERGE (d1)-[:IS_LINKED_WITH]->(d2)
"""


# ─── Helpers ─────────────────────────────────────────────────────────────────

def clean_value(val: str) -> str | None:
    """Clean a CSV cell value. Return None if empty/missing."""
    if val is None:
        return None
    val = str(val).strip()
    if val in ("", "nan", "None", "NaN"):
        return None
    return val


def capitalize_first(text: str) -> str:
    """Capitalize the first letter of a string."""
    if text and isinstance(text, str):
        return text[0].upper() + text[1:]
    return text


def read_csv(csv_path: Path) -> list[dict]:
    """Read CSV and return list of dicts with English column names."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            row = {}
            for vn_col, en_col in COL_MAP.items():
                val = clean_value(raw_row.get(vn_col))
                if en_col == "disease_name" and val:
                    val = capitalize_first(val)
                row[en_col] = val
            rows.append(row)
    log.info(f"Read {len(rows)} rows from {csv_path.name}")
    return rows


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# ─── Import Functions ────────────────────────────────────────────────────────

def create_constraints(driver):
    """Create uniqueness constraints (idempotent)."""
    log.info("Creating constraints...")
    with driver.session() as session:
        for query in CONSTRAINTS_QUERIES:
            session.run(query)
    log.info(f"{len(CONSTRAINTS_QUERIES)} constraints created/verified")


def clear_graph(driver):
    """Delete all nodes and relationships. Use with caution!"""
    log.warning("Clearing entire graph...")
    with driver.session() as session:
        result = session.run("MATCH (n) DETACH DELETE n")
        summary = result.consume()
        log.info(f"Deleted {summary.counters.nodes_deleted} nodes, "
                 f"{summary.counters.relationships_deleted} relationships")


def import_nodes(driver, rows: list[dict], query: str, label: str, batch_size: int):
    """Import nodes in batches using UNWIND."""
    total = 0
    for i, batch in enumerate(chunks(rows, batch_size)):
        with driver.session() as session:
            result = session.run(query, rows=batch)
            summary = result.consume()
            created = summary.counters.nodes_created
            total += created
            log.info(f"  {label} batch {i+1}: +{created} nodes "
                     f"({summary.counters.relationships_created} rels)")
    return total


def import_linked_diseases(driver, rows: list[dict], batch_size: int):
    """Import IS_LINKED_WITH relationships (second pass).
    Handles comma-separated associated diseases.
    """
    linked_rows = []
    for row in rows:
        assoc = row.get("associated_disease")
        if not assoc or assoc == "Không có thông tin":
            continue
        # Handle list-like values: "[A, B, C]" or "A, B"
        assoc_clean = assoc.strip().strip("[]")
        names = [capitalize_first(n.strip().strip("'\""))
                 for n in assoc_clean.split(",") if n.strip()]
        for name in names:
            if name and name != row["disease_name"]:
                linked_rows.append({
                    "disease_name": row["disease_name"],
                    "associated_disease": name,
                })

    log.info(f"Found {len(linked_rows)} IS_LINKED_WITH pairs")
    total_rels = 0
    for i, batch in enumerate(chunks(linked_rows, batch_size)):
        with driver.session() as session:
            result = session.run(IMPORT_LINKED_QUERY, rows=batch)
            summary = result.consume()
            total_rels += summary.counters.relationships_created
    log.info(f"Created {total_rels} IS_LINKED_WITH relationships")
    return total_rels


def validate_graph(driver):
    """Run validation queries to verify import."""
    log.info("=" * 50)
    log.info("VALIDATION")
    log.info("=" * 50)

    with driver.session() as session:
        # Count nodes by label
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS label, COUNT(n) AS count
            ORDER BY count DESC
        """)
        log.info("Node counts:")
        total_nodes = 0
        for record in result:
            log.info(f"  {record['label']}: {record['count']}")
            total_nodes += record["count"]
        log.info(f"  TOTAL: {total_nodes}")

        # Count relationships by type
        result = session.run("""
            MATCH ()-[r]->()
            RETURN TYPE(r) AS type, COUNT(r) AS count
            ORDER BY count DESC
        """)
        log.info("Relationship counts:")
        total_rels = 0
        for record in result:
            log.info(f"  {record['type']}: {record['count']}")
            total_rels += record["count"]
        log.info(f"  TOTAL: {total_rels}")

        # Sample query: a disease with all info
        result = session.run("""
            MATCH (d:Disease)
            WHERE d.disease_description IS NOT NULL
            WITH d LIMIT 1
            OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
            OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
            OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine)
            OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
            RETURN d.disease_name AS name,
                   s.disease_symptom AS symptoms,
                   t.cure_method AS treatment,
                   m.drug_common AS medicine,
                   a.disease_prevention AS advice
        """)
        record = result.single()
        if record:
            log.info(f"\nSample Disease: {record['name']}")
            for key in ["symptoms", "treatment", "medicine", "advice"]:
                val = record[key]
                if val:
                    log.info(f"  {key}: {str(val)[:100]}...")


def dry_run(rows: list[dict]):
    """Print stats without connecting to Neo4j."""
    log.info("=" * 50)
    log.info("DRY RUN — No Neo4j connection")
    log.info("=" * 50)

    total = len(rows)
    diseases = set()
    has_symptom = 0
    has_treatment = 0
    has_medicine = 0
    has_advice = 0
    has_linked = 0

    for row in rows:
        diseases.add(row["disease_name"])
        if row.get("disease_symptom") and row["disease_symptom"] != "Không có thông tin":
            has_symptom += 1
        if row.get("cure_method") and row["cure_method"] != "Không có thông tin":
            has_treatment += 1
        if row.get("drug_common") and row["drug_common"] != "Không có thông tin":
            has_medicine += 1
        if (row.get("nutrition_do_eat") and row["nutrition_do_eat"] != "Không có thông tin") or \
           (row.get("disease_prevention") and row["disease_prevention"] != "Không có thông tin"):
            has_advice += 1
        if row.get("associated_disease") and row["associated_disease"] != "Không có thông tin":
            has_linked += 1

    log.info(f"Total CSV rows: {total}")
    log.info(f"Unique diseases: {len(diseases)}")
    log.info(f"Rows with symptoms: {has_symptom}")
    log.info(f"Rows with treatment: {has_treatment}")
    log.info(f"Rows with medicine: {has_medicine}")
    log.info(f"Rows with advice: {has_advice}")
    log.info(f"Rows with linked disease: {has_linked}")
    log.info(f"\nEstimated nodes: ~{len(diseases) + has_symptom + has_treatment + has_medicine + has_advice}")
    log.info(f"Estimated relationships: ~{has_symptom + has_treatment + has_medicine + has_advice + has_linked}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import VietMedKG data into Neo4j")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse CSV and print stats without importing")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Number of rows per batch (default: 500)")
    parser.add_argument("--clear", action="store_true",
                        help="Clear existing graph before import")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to CSV file (default: auto-detect)")
    args = parser.parse_args()

    # Resolve CSV path
    csv_path = Path(args.csv) if args.csv else CSV_FILE
    if not csv_path.exists():
        log.error(f"CSV file not found: {csv_path}")
        log.error("Run: git clone https://github.com/HySonLab/VietMedKG.git ai-engine/data/vietmedkg")
        sys.exit(1)

    # Read data
    rows = read_csv(csv_path)
    if not rows:
        log.error("No data found in CSV")
        sys.exit(1)

    # Dry run mode
    if args.dry_run:
        dry_run(rows)
        return

    # Load .env for Neo4j credentials
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        log.error(f".env file not found at {env_path}")
        log.error("Create .env with: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD")
        sys.exit(1)
    load_dotenv(env_path)

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not uri or not password:
        log.error("Missing NEO4J_URI or NEO4J_PASSWORD in .env")
        sys.exit(1)

    # Connect to Neo4j
    log.info(f"Connecting to {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    log.info("Connected to Neo4j")

    try:
        # Optional: clear graph
        if args.clear:
            clear_graph(driver)

        # Create constraints
        create_constraints(driver)

        bs = args.batch_size

        # Import nodes + relationships
        log.info(f"\n{'='*50}")
        log.info(f"IMPORTING {len(rows)} rows (batch size: {bs})")
        log.info(f"{'='*50}")

        log.info("\n[1/5] Importing Disease nodes...")
        import_nodes(driver, rows, IMPORT_DISEASE_QUERY, "Disease", bs)

        log.info("\n[2/5] Importing Symptom nodes + HAS_SYMPTOM...")
        import_nodes(driver, rows, IMPORT_SYMPTOM_QUERY, "Symptom", bs)

        log.info("\n[3/5] Importing Treatment nodes + HAS_TREATMENT...")
        import_nodes(driver, rows, IMPORT_TREATMENT_QUERY, "Treatment", bs)

        log.info("\n[4/5] Importing Medicine nodes + IS_PRESCRIBED...")
        import_nodes(driver, rows, IMPORT_MEDICINE_QUERY, "Medicine", bs)

        log.info("\n[5/5] Importing Advice nodes + HAS_ADVICE...")
        import_nodes(driver, rows, IMPORT_ADVICE_QUERY, "Advice", bs)

        log.info("\n[BONUS] Importing IS_LINKED_WITH relationships...")
        import_linked_diseases(driver, rows, bs)

        # Validate
        log.info("")
        validate_graph(driver)

        log.info("\nImport completed successfully!")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
