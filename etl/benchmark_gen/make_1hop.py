"""
make_1hop.py

Generates 1-hop questions from triples using OpenAI's gpt-4o-mini.
Implements multi-threading for fast processing.
"""

import os
import json
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import openai

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
INPUT_JSON = BASE_DIR / "benchmark" / "triples.json"
OUTPUT_1HOP = BASE_DIR / "benchmark" / "1hop.json"

# Load environment variables
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

# Ensure OpenAI API key is present
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    log.error("OPENAI_API_KEY environment variable is not set (load it via .env or export it).")
    raise SystemExit(1)

client = openai.OpenAI(api_key=api_key)

RELATION_DICT = {
    "disease_description": "mô_tả",
    "disease_category": "loại",
    "disease_prevention": "cách_phòng_tránh",
    "disease_cause": "nguyên_nhân",
    "disease_symptom": "triệu_chứng",
    "people_easy_get": "đối_tượng_dễ_mắc_bệnh",
    "associated_disease": "bệnh_đi_kèm",
    "cure_department": "khoa_điều_trị",
    "cure_method": "phương_pháp_điều_trị",
    "cure_probability": "tỉ_lệ_chữa_khỏi",
    "check_method": "kiểm_tra",
    "nutrition_do_eat": "thực_phẩm_nên_ăn",
    "nutrition_not_eat": "thực_phẩm_không_nên_ăn",
    "nutrition_recommend_eat": "món_ăn_được_đề_xuất",
    "drug_recommend": "thuốc_đề_xuất",
    "drug_common": "thuốc_phổ_biến",
    "drug_detail": "thông_tin_về_thuốc"
}

def get_gpt_response(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content
    except Exception as e:
        log.error(f"OpenAI API Error: {e}")
        return ""

class QuestionGenerator:
    def __init__(self, mode="benh_to_X"):
        self.mode = mode

    def create_template(self, item):
        rel = RELATION_DICT.get(item['relation'])
        if not rel:
            return None
            
        if self.mode == "benh_to_X":
            templates = {
                'mô_tả': f"Mô tả về [{item['header']}]?",
                'loại': f"[{item['header']}] thuộc loại bệnh nào?",
                'cách_phòng_tránh': f"Cách phòng tránh [{item['header']}]?",
                'nguyên_nhân': f"Nguyên nhân dẫn đến [{item['header']}]?",
                'triệu_chứng': f"Triệu chứng của [{item['header']}]?",
                'đối_tượng_dễ_mắc_bệnh': f"Đối tượng dễ mắc [{item['header']}]?",
                'bệnh_đi_kèm': f"Các bệnh thường xảy ra cùng với [{item['header']}]?",
                'khoa_điều_trị': f"Bạn có thể đến khoa nào để điều trị [{item['header']}]?",
                'phương_pháp_điều_trị': f"Phương pháp điều trị [{item['header']}]?",
                'tỉ_lệ_chữa_khỏi': f"Tỉ lệ chữa khỏi [{item['header']}]?",
                'kiểm_tra': f"Bạn cần kiểm tra những gì khi mắc [{item['header']}]?",
                'thực_phẩm_nên_ăn': f"Thực phẩm nên ăn trong quá trình chữa [{item['header']}]?",
                'thực_phẩm_không_nên_ăn': f"Thực phẩm không nên ăn trong quá trình chữa [{item['header']}]?",
                'món_ăn_được_đề_xuất': f"Món ăn nên ăn trong quá trình chữa [{item['header']}]?",
                'thuốc_đề_xuất': f"Các loại thuốc được đề xuất khi chữa [{item['header']}]?",
                'thuốc_phổ_biến': f"Các loại thuốc phổ biến được dùng để chữa [{item['header']}]?",
                'thông_tin_về_thuốc': f"Thông tin chi tiết về thuốc để chữa [{item['header']}]?"
            }
            return templates.get(rel)
        else:
            # X_to_benh mode
            templates = {
                'mô_tả': f"[{item['tail']}] là mô tả của bệnh gì?",
                'loại': f"Các loại bệnh [{item['tail']}] có thể dùng để chỉ bệnh gì?",
                'cách_phòng_tránh': f"Cách phòng tránh [{item['tail']}] có thể được dùng cho bệnh gì?",
                'nguyên_nhân': f"Các nguyên nhân [{item['tail']}] có thể dẫn đến bệnh gì?",
                'triệu_chứng': f"Các triệu chứng [{item['tail']}] có thể là của bệnh gì?",
                'đối_tượng_dễ_mắc_bệnh': f"Các đối tượng [{item['tail']}] thường dễ mắc bệnh gì?",
                'bệnh_đi_kèm': f"Các bệnh [{item['tail']}] xảy ra cùng lúc có thể là dấu hiệu của bệnh gì?",
                'khoa_điều_trị': f"Bạn có thể đến khoa [{item['tail']}] để điều trị bệnh nào?",
                'phương_pháp_điều_trị': f"Phương pháp điều trị [{item['tail']}] có thể dùng để điều trị bệnh nào?",
                'kiểm_tra': f"Kiểm tra [{item['tail']}] khi bạn nghi ngờ mắc bệnh gì?",
                'thực_phẩm_nên_ăn': f"Thực phẩm nên ăn [{item['tail']}] có thể hỗ trợ chữa bệnh gì?",
                'thực_phẩm_không_nên_ăn': f"Thực phẩm không nên ăn [{item['tail']}] có thể hỗ trợ chữa bệnh gì?",
                'món_ăn_được_đề_xuất': f"Món ăn nên ăn [{item['tail']}] có thể hỗ trợ chữa bệnh gì?",
                'thuốc_đề_xuất': f"Các loại thuốc [{item['tail']}] được đề xuất khi chữa bệnh gì?",
                'thuốc_phổ_biến': f"Các loại thuốc phổ biến [{item['tail']}] được dùng để chữa bệnh gì?"
            }
            return templates.get(rel)

    def rephrase_question(self, raw_question: str) -> str:
        prompt = f"""Imagine you are a doctor managing a large number of patients and receiving numerous questions daily.
        Based on the provided question [{raw_question}], create a human-like question that a patient might ask. 
        Return the question in JSON format, preserving the brackets [] in the question exactly as they are.
        For example: {{"question": "Bác sĩ ơi, bệnh nhân mắc [Tiểu đường] thì nên ăn gì?"}}
        Limit the question length to 25 words. Do not drop the bracketed entity.
        If the question doesn't make sense, return {{}}.
        """
        response_text = get_gpt_response(prompt)
        
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                return data.get("question", "")
        except:
            return ""
        return ""

    def process_item(self, item):
        raw_question = self.create_template(item)
        if not raw_question:
            return None
            
        rephrased = self.rephrase_question(raw_question)
        if not rephrased:
            return None
            
        answer = item['tail'] if self.mode == "benh_to_X" else item['header']
        q_type = RELATION_DICT.get(item['relation'])
        if self.mode == "benh_to_X":
            q_type = f"bệnh_đến_{q_type}"
        else:
            q_type = f"{q_type}_đến_bệnh"
            
        return {
            "question": rephrased,
            "question_type": q_type,
            "answer": answer
        }

def run_pipeline(sample_size=None):
    if not INPUT_JSON.exists():
        log.error(f"Input file not found: {INPUT_JSON}")
        return

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        triples = json.load(f)
        
    if sample_size:
        triples = triples[:sample_size]
        
    log.info(f"Processing {len(triples)} triples to generate 1-hop questions...")
    
    gen_b2x = QuestionGenerator("benh_to_X")
    gen_x2b = QuestionGenerator("X_to_benh")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        # Submit both types of questions for each triple
        futures = []
        for item in triples:
            futures.append(executor.submit(gen_b2x.process_item, item))
            if item['relation'] != 'cure_probability': # Skip this for X to Benh
                futures.append(executor.submit(gen_x2b.process_item, item))
                
        for future in tqdm(as_completed(futures), total=len(futures), desc="Calling OpenAI"):
            res = future.result()
            if res:
                results.append(res)
                
    OUTPUT_1HOP.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_1HOP, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    log.info(f"Successfully saved {len(results)} questions to {OUTPUT_1HOP}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="Limit number of triples to process (for testing)")
    args = parser.parse_args()
    
    run_pipeline(sample_size=args.sample)
