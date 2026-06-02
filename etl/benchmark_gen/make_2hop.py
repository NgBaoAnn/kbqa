"""
make_2hop.py

Generates 2-hop questions by chaining relations (e.g. Associated Disease -> Treatment).
Uses OpenAI gpt-4o-mini to rephrase questions naturally.
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
OUTPUT_2HOP = BASE_DIR / "benchmark" / "2hop.json"

# Load environment variables
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    log.error("OPENAI_API_KEY not found in .env file.")
    exit(1)

client = openai.OpenAI(api_key=api_key)

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

def rephrase_question(raw_question: str) -> str:
    prompt = f"""Imagine you are a doctor managing patients.
    Rephrase this question [{raw_question}] into a natural question asked by a patient.
    Return in JSON format: {{"question": "..."}}. 
    Preserve the exact brackets [] around the entity. Limit to 25 words.
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
        pass
    return ""

def process_item(disease, associated_disease, relation_type, answer):
    # Example 2-hop logic: "What is the [treatment] for the disease associated with [disease]?"
    # To match VietMedKG style: "Phương pháp điều trị của những bệnh đi kèm như [Associated_disease] là gì?"
    relation_map = {
        "cure_method": "phương pháp điều trị",
        "drug_common": "thuốc phổ biến",
        "disease_symptom": "triệu chứng"
    }
    rel_str = relation_map.get(relation_type)
    if not rel_str:
        return None
        
    raw_q = f"{rel_str.capitalize()} của những bệnh đi kèm như [{associated_disease}] là gì?"
    
    rephrased = rephrase_question(raw_q)
    if not rephrased:
        return None
        
    return {
        "question": rephrased,
        "question_type": f"bệnh_đi_kèm_đến_{rel_str.replace(' ', '_')}",
        "answer": answer
    }

def run_pipeline(sample_size=None):
    if not INPUT_JSON.exists():
        log.error(f"Input file not found: {INPUT_JSON}")
        return

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        triples = json.load(f)
        
    # Group properties by disease to find 2-hop links
    disease_dict = {}
    for t in triples:
        head = t['header']
        rel = t['relation']
        tail = t['tail']
        if head not in disease_dict:
            disease_dict[head] = {}
        if rel not in disease_dict[head]:
            disease_dict[head][rel] = []
        disease_dict[head][rel].append(tail)
        
    tasks = []
    for head, props in disease_dict.items():
        if "associated_disease" in props:
            for assoc in props["associated_disease"]:
                # Split multiple associated diseases
                assoc_list = [a.strip() for a in assoc.split(',')]
                for a in assoc_list:
                    # If the associated disease is also in our dict
                    if a in disease_dict:
                        for rel in ["cure_method", "drug_common", "disease_symptom"]:
                            if rel in disease_dict[a]:
                                answer = " | ".join(disease_dict[a][rel])
                                tasks.append((head, a, rel, answer))
                                
    if sample_size:
        tasks = tasks[:sample_size]
        
    log.info(f"Processing {len(tasks)} tasks to generate 2-hop questions...")
    results = []
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_item, *task): task for task in tasks}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Calling OpenAI"):
            res = future.result()
            if res:
                results.append(res)
                
    OUTPUT_2HOP.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_2HOP, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    log.info(f"Successfully saved {len(results)} questions to {OUTPUT_2HOP}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="Limit number of questions to process")
    args = parser.parse_args()
    
    run_pipeline(sample_size=args.sample)
