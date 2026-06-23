import os
import argparse
import asyncio
import pandas as pd
from tqdm.auto import tqdm
from dotenv import load_dotenv
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from lightrag import LightRAG
from lightrag.llm.openai import openai_complete
from lightrag.llm.ollama import ollama_embed
from lightrag.utils import EmbeddingFunc

# Tải cấu hình từ file .env ở thư mục gốc
load_dotenv(".env", override=True)

# Ghi đè cấu hình OpenAI cho 9router
os.environ["OPENAI_API_BASE"] = os.environ.get("OPENAI_API_BASE", "http://localhost:20128/v1")
os.environ["OPENAI_BASE_URL"] = os.environ["OPENAI_API_BASE"]
os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "sk-dummy-key") # Thay bằng key thật của 9router trong file .env
os.environ["LIGHTRAG_WORKSPACE"] = "base" # Namespace mặc định

async def main():
    parser = argparse.ArgumentParser(description="Chạy Ingest dữ liệu cho LightRAG")
    parser.add_argument("--retry", action="store_true", help="Chạy chế độ vá lỗi (KHÔNG xóa Database cũ, quét lại toàn bộ để vá FAILED)")
    args = parser.parse_args()

    print("==================================================")
    if args.retry:
        print("🚀 BẮT ĐẦU QUÁ TRÌNH INGEST - CHẾ ĐỘ RETRY (VÁ LỖI)")
    else:
        print("🚀 BẮT ĐẦU QUÁ TRÌNH INGEST VỚI 9ROUTER (LOCAL)")
    print("==================================================\n")

    # Đọc checkpoint trước để quyết định có xóa DB hay không
    CHECKPOINT_FILE = "ingest_9router_checkpoint.txt"
    start_index = 0
    
    if args.retry:
        print("🔄 CHẾ ĐỘ RETRY: Sẽ quét lại toàn bộ dữ liệu từ đầu để vá các file FAILED.")
    elif os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                start_index = int(f.read().strip())
                print(f"🔄 Tìm thấy checkpoint! Tiếp tục nạp từ index: {start_index}")
        except Exception:
            pass

    # ---------------------------------------------------------
    # 1. DỌN DẸP DỮ LIỆU CŨ (CLEANUP)
    # ---------------------------------------------------------
    if not args.retry and start_index == 0:
        print("🧹 BƯỚC 1: DỌN DẸP DỮ LIỆU CŨ (Do chạy mới hoàn toàn)...")
        try:
            print("   Đang kết nối Neo4j...")
            driver = GraphDatabase.driver(
                os.environ.get("NEO4J_URI", "neo4j://localhost:7687"), 
                auth=(os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
            )
            with driver.session() as session:
                result = session.run("MATCH (n:base) DETACH DELETE n RETURN count(n) as deleted_count")
                record = result.single()
                deleted = record["deleted_count"] if record else 0
                print(f"   ✅ Đã xóa {deleted} nodes cũ trong Neo4j.")
            driver.close()
        except Exception as e:
            print(f"   ⚠️ Lỗi dọn dẹp Neo4j: {e}")

        try:
            print("   Đang kết nối Qdrant...")
            qdrant = QdrantClient(
                url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
                api_key=os.environ.get("QDRANT_API_KEY")
            )
            collections_to_delete = ["lightrag_vdb_chunks", "lightrag_vdb_entities", "lightrag_vdb_relationships"]
            for col in collections_to_delete:
                try:
                    qdrant.delete_collection(col)
                    print(f"   ✅ Đã xóa collection {col} trên Qdrant.")
                except Exception:
                    pass
        except Exception as e:
            print(f"   ⚠️ Lỗi kết nối Qdrant: {e}")
            
        print("✨ HOÀN TẤT DỌN DẸP!\n")
    else:
        print("⏭️ BƯỚC 1: Bỏ qua dọn dẹp Database (An toàn dữ liệu).\n")

    # ---------------------------------------------------------
    # 2. KHỞI TẠO LIGHTRAG
    # ---------------------------------------------------------
    print("⚙️ BƯỚC 2: KHỞI TẠO LIGHTRAG...")
    WORKING_DIR = "./lightrag_data"
    if not os.path.exists(WORKING_DIR):
        os.makedirs(WORKING_DIR)

    # Cấu hình hàm nhúng (Chạy Ollama Local)
    emb_func = EmbeddingFunc(
        embedding_dim=1024,
        max_token_size=8192,
        model_name="bge-m3",
        func=lambda texts: ollama_embed(
            texts, 
            embed_model="bge-m3", 
            host="http://localhost:11434" # Trỏ thẳng về Ollama dưới máy
        )
    )

    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=openai_complete,  # Dùng OpenAI API format
        llm_model_name="ag/gemini-3-flash",       # Model 9router của bạn
        
        llm_model_max_async=5, 
        embedding_func_max_async=4,               
        
        default_llm_timeout=1200,                 
        default_embedding_timeout=1200,
        
        embedding_func=emb_func,
        graph_storage="Neo4JStorage",
        vector_storage="QdrantVectorDBStorage",
        kv_storage="JsonKVStorage",
        addon_params={"language": "Vietnamese"}
    )

    await rag.initialize_storages()
    print("✅ LightRAG đã sẵn sàng với Neo4j, Qdrant và 9router!\n")

    # ---------------------------------------------------------
    # 3. ĐỌC DỮ LIỆU CSV
    # ---------------------------------------------------------
    print("📖 BƯỚC 3: ĐỌC DỮ LIỆU...")
    CSV_PATH = "data/preprocessed_data.csv"
    if not os.path.exists(CSV_PATH):
        print(f"❌ Không tìm thấy file {CSV_PATH}. Vui lòng kiểm tra lại đường dẫn!")
        return

    df = pd.read_csv(CSV_PATH)
    print(f"   Tổng số dòng: {len(df)}")

    documents = []
    for _, row in df.iterrows():
        text = f"Bệnh: {row.get('disease_name', '')}\n"
        text += f"Mô tả: {row.get('disease_description', '')}\n"
        
        val_symp = row.get('disease_symptom')
        if isinstance(val_symp, str) and val_symp.strip():
            text += f"Triệu chứng: {val_symp}\n"
        val_cause = row.get('disease_cause')
        if isinstance(val_cause, str) and val_cause.strip():
            text += f"Nguyên nhân: {val_cause}\n"
        val_cure = row.get('cure_method')
        if isinstance(val_cure, str) and val_cure.strip():
            text += f"Điều trị: {val_cure}\n"
            
        documents.append(text.strip())

    # ---------------------------------------------------------
    # 4. BẮT ĐẦU INGEST
    # ---------------------------------------------------------
    print("\n🚀 BƯỚC 4: BẮT ĐẦU INGEST VÀO LIGHTRAG...")
    BATCH_SIZE = 25

    total_docs = len(documents)
    
    # Dùng tqdm để hiển thị thanh tiến trình
    pbar = tqdm(range(start_index, total_docs, BATCH_SIZE), desc="Ingesting Batches")
    
    for i in pbar:
        batch_docs = documents[i : i + BATCH_SIZE]
        
        # Đẩy dữ liệu vào LightRAG
        await rag.ainsert(batch_docs)
        
        # Chỉ lưu checkpoint khi không ở chế độ retry (vì retry chạy lướt qua toàn bộ)
        if not args.retry:
            with open(CHECKPOINT_FILE, "w") as f:
                f.write(str(i + BATCH_SIZE))
            
    print("\n🎉 XONG! Dữ liệu đã đồng bộ hoàn hảo với hệ thống.")
    if not args.retry and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

if __name__ == "__main__":
    # Khởi chạy luồng chính
    asyncio.run(main())
