"""
Đồng bộ LightRAG entities + relationships từ Qdrant → Neo4j.

Mục đích:
  Notebook kaggle_ingest_entities_relationships.ipynb đã nạp 34,955 entities
  và 48,125 relationships vào Qdrant (lightrag_vdb_entities / lightrag_vdb_relationships).
  Nhưng LightRAG local/global/mix mode còn cần Neo4j làm KG layer để:
    - get_nodes_batch()       → lấy node properties
    - node_degrees_batch()    → lấy degree
    - get_nodes_edges_batch() → duyệt graph neighbors
  Script này đọc payload từ Qdrant và MERGE vào Neo4j với label :base
  (workspace mặc định LightRAG đang dùng).

Cách dùng:
  NO_PROXY="" no_proxy="" .venv/bin/python scripts/ingest_to_neo4j.py

Ghi chú:
  - Dùng MERGE (không phải CREATE) → chạy nhiều lần an toàn (idempotent)
  - Label :base không đụng chạm :Disease :Symptom :Treatment... của VietMedKG
  - Edges được tạo với type :DIRECTED theo đúng neo4j_impl.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# ── Env vars fix (httpx 0.28.x bug với IPv6 CIDR trong NO_PROXY) ──────────
os.environ["NO_PROXY"] = ""
os.environ["no_proxy"] = ""

# ── Project root on path ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from qdrant_client import QdrantClient
from qdrant_client import models as qm

# ── Config ─────────────────────────────────────────────────────────────────
QDRANT_URL     = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]

# workspace_id trong Qdrant payload (do notebook ingest dùng "_")
QDRANT_WORKSPACE = "_"

# workspace label trong Neo4j (LightRAG dùng "base" khi WORKSPACE env không set)
NEO4J_WORKSPACE  = "base"

ENTITY_COLLECTION = "lightrag_vdb_entities"
REL_COLLECTION    = "lightrag_vdb_relationships"
SCROLL_BATCH      = 1000   # số points mỗi lần scroll Qdrant
NEO4J_BATCH_SIZE  = 2000   # số nodes/edges mỗi lần UNWIND vào Neo4j

CREATED_AT = int(time.time())


# ── Qdrant helpers ──────────────────────────────────────────────────────────

def ws_filter() -> qm.Filter:
    return qm.Filter(
        must=[qm.FieldCondition(
            key="workspace_id",
            match=qm.MatchValue(value=QDRANT_WORKSPACE)
        )]
    )


def scroll_all(client: QdrantClient, collection: str):
    """Paginate through all points in a Qdrant collection."""
    offset = None
    while True:
        result, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=ws_filter(),
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        yield from result
        if next_offset is None:
            break
        offset = next_offset


# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    # ── 0. Init shared_storage (cần thiết để Neo4JStorage hoạt động) ────────
    from lightrag.kg.shared_storage import initialize_share_data
    initialize_share_data()

    # ── 1. Kết nối Qdrant ────────────────────────────────────────────────────
    print(f"🔌 Connecting to Qdrant: {QDRANT_URL[:55]}...")
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    for col in [ENTITY_COLLECTION, REL_COLLECTION]:
        try:
            n = qdrant.count(col, count_filter=ws_filter(), exact=True).count
            print(f"   {col}: {n:,} points (workspace='{QDRANT_WORKSPACE}')")
        except Exception as e:
            print(f"   ⚠️  {col}: {e}")

    # ── 2. Init Neo4JStorage ─────────────────────────────────────────────────
    from lightrag.kg.neo4j_impl import Neo4JStorage
    print(f"\n🔌 Connecting to Neo4j (workspace='{NEO4J_WORKSPACE}')...")
    storage = Neo4JStorage(
        namespace="chunk_entity_relation",
        global_config={},
        embedding_func=None,
        workspace=NEO4J_WORKSPACE,
    )
    await storage.initialize()
    print(f"   Neo4j label: :{storage._get_workspace_label()}")

    # ── 3. Đọc entities từ Qdrant ────────────────────────────────────────────
    print("\n📥 Đang đọc entities từ Qdrant...")
    entities_batch: list[tuple[str, dict]] = []
    known_entities: set[str] = set()

    for pt in scroll_all(qdrant, ENTITY_COLLECTION):
        p = pt.payload or {}
        name = p.get("entity_name", "").strip()
        if not name:
            continue

        known_entities.add(name)
        entities_batch.append((
            name,
            {
                "entity_id":   name,
                "description": p.get("content", name),
                "entity_type": p.get("entity_type", "concept"),
                "source_id":   p.get("source_id", ""),
                "file_path":   p.get("file_path", "unknown_source"),
                "created_at":  CREATED_AT,
                "truncate":    "",
            }
        ))

        if len(entities_batch) % 5000 == 0:
            print(f"   {len(entities_batch):,} entities loaded...")

    print(f"   ✅ {len(entities_batch):,} entities đọc xong.")

    # ── 4. Đọc relationships từ Qdrant ──────────────────────────────────────
    print("\n📥 Đang đọc relationships từ Qdrant...")
    rels_batch: list[tuple[str, str, dict]] = []
    ghost_nodes: dict[str, dict] = {}   # nodes thiếu cần tạo placeholder

    for pt in scroll_all(qdrant, REL_COLLECTION):
        p = pt.payload or {}
        src = p.get("src_id", "").strip()
        tgt = p.get("tgt_id", "").strip()
        if not src or not tgt:
            continue

        # Tạo placeholder cho endpoint thiếu
        for node_name in (src, tgt):
            if node_name not in known_entities and node_name not in ghost_nodes:
                ghost_nodes[node_name] = (
                    node_name,
                    {
                        "entity_id":   node_name,
                        "description": node_name,
                        "entity_type": "concept",
                        "source_id":   "",
                        "file_path":   "unknown_source",
                        "created_at":  CREATED_AT,
                        "truncate":    "",
                    }
                )

        rels_batch.append((
            src,
            tgt,
            {
                "weight":      float(p.get("weight", 1.0)),
                "description": p.get("description", ""),
                "keywords":    p.get("keywords", ""),
                "source_id":   p.get("source_id", ""),
                "file_path":   p.get("file_path", "unknown_source"),
                "created_at":  CREATED_AT,
                "truncate":    "",
            }
        ))

        if len(rels_batch) % 10000 == 0:
            print(f"   {len(rels_batch):,} relationships loaded...")

    print(f"   ✅ {len(rels_batch):,} relationships đọc xong.")

    if ghost_nodes:
        print(f"   ℹ️  {len(ghost_nodes):,} endpoint nodes thiếu → sẽ tạo placeholder.")
        entities_batch.extend(ghost_nodes.values())

    # ── 5. MERGE nodes vào Neo4j ─────────────────────────────────────────────
    total_nodes = len(entities_batch)
    print(f"\n⬆️  Đang MERGE {total_nodes:,} nodes vào Neo4j...")
    for i in range(0, total_nodes, NEO4J_BATCH_SIZE):
        chunk = entities_batch[i : i + NEO4J_BATCH_SIZE]
        await storage.upsert_nodes_batch(chunk)
        print(f"   nodes {i:>6,} → {min(i + NEO4J_BATCH_SIZE, total_nodes):>6,} ✓")

    print(f"   ✅ Node ingestion hoàn thành.")

    # ── 6. MERGE edges vào Neo4j ─────────────────────────────────────────────
    total_rels = len(rels_batch)
    print(f"\n⬆️  Đang MERGE {total_rels:,} edges vào Neo4j...")
    for i in range(0, total_rels, NEO4J_BATCH_SIZE):
        chunk = rels_batch[i : i + NEO4J_BATCH_SIZE]
        await storage.upsert_edges_batch(chunk)
        print(f"   edges {i:>6,} → {min(i + NEO4J_BATCH_SIZE, total_rels):>6,} ✓")

    print(f"   ✅ Edge ingestion hoàn thành.")

    # ── 7. Verify ────────────────────────────────────────────────────────────
    print(f"\n🔍 Verify Neo4j...")
    async with storage._driver.session(database=storage._DATABASE) as session:
        label = storage._get_workspace_label()
        node_count = await session.run(
            f"MATCH (n:`{label}`) RETURN count(n) as c"
        )
        n = await node_count.single()
        print(f"   :base nodes  = {n['c']:,}")

        edge_count = await session.run(
            f"MATCH (a:`{label}`)-[r:DIRECTED]-(b:`{label}`) RETURN count(r) as c"
        )
        e = await edge_count.single()
        print(f"   :DIRECTED edges = {e['c']:,}")

    await storage.finalize()

    # ── 8. Hướng dẫn bước tiếp theo ─────────────────────────────────────────
    print("""
🎉 Đồng bộ hoàn tất!

Bước tiếp theo — sửa .env:
    FORCE_LIGHTRAG_NAIVE_MODE=false
    DEFAULT_QUERY_MODE=local

Sau đó restart backend:
    uvicorn backend.app.main:app --reload

Test thử:
    curl -X POST http://localhost:8000/api/query \\
         -H "Content-Type: application/json" \\
         -d '{"question": "bệnh tiểu đường có triệu chứng gì?", "language": "vi"}'
""")


if __name__ == "__main__":
    asyncio.run(main())
