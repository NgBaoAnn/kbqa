"""
make_multi_answer.py

Groups similar questions and concatenates their answers using '|'.
This reduces redundancy and combines all valid answers for a given question.
"""

import json
import re
import logging
from collections import defaultdict
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def extract_content(question: str) -> str:
    """Extract content within square brackets from the question."""
    try: 
        return re.search(r'\[(.*?)\]', question).group(1).lower()
    except:
        return None

def jaccard_similarity(set1: set, set2: set) -> float:
    """Compute the Jaccard similarity score between two sets of words."""
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    if union == 0:
        return 0.0
    return intersection / union

def remove_duplicates(list_of_dicts: list) -> list:
    """Remove duplicate dictionaries from a list of dictionaries."""
    seen = set()
    unique_dicts = []
    for d in list_of_dicts:
        # Convert dictionary to a frozen set of items to make it hashable
        dict_tuple = frozenset(d.items())
        if dict_tuple not in seen:
            seen.add(dict_tuple)
            unique_dicts.append(d)
    return unique_dicts

def process_file(input_file: Path):
    if not input_file.exists():
        log.error(f"File not found: {input_file}")
        return

    log.info(f"Processing {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    data = remove_duplicates(data)
    grouped_data = defaultdict(list)
    merged_data = []

    for item in data:
        q_type = item.get("question_type")
        content = extract_content(item.get("question", ""))
        if not content or not q_type:
            continue
        item["content"] = content
        grouped_data[q_type].append(item)

    for q_type, items in grouped_data.items():
        while items:
            base_item = items.pop(0)
            similar_items = [base_item]
            
            # Find all items with similar entity content
            base_words = set(base_item["content"].split())
            items_to_remove = []
            
            for other_item in items:
                other_words = set(other_item["content"].split())
                similarity = jaccard_similarity(base_words, other_words)
                
                if similarity >= 0.9:
                    similar_items.append(other_item)
                    items_to_remove.append(other_item)
                    
            for r in items_to_remove:
                items.remove(r)
            
            merged_question = base_item["question"]
            
            # Gather all answers and join with |
            all_answers = []
            for sim_item in similar_items:
                # If an answer already contains commas or |, split it first
                ans = str(sim_item["answer"])
                ans_parts = [a.strip() for a in ans.replace('|', ',').split(',')]
                for p in ans_parts:
                    if p and p not in all_answers:
                        all_answers.append(p)
                        
            merged_answer = "|".join(all_answers)
            
            merged_data.append({
                "question": merged_question,
                "question_type": q_type,
                "answer": merged_answer
            })
            
    with open(input_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=4)
        
    log.info(f"Successfully grouped answers. Reduced to {len(merged_data)} unique questions.")

if __name__ == "__main__":
    file_1hop = BASE_DIR / "benchmark" / "1hop.json"
    file_2hop = BASE_DIR / "benchmark" / "2hop.json"
    
    process_file(file_1hop)
    process_file(file_2hop)
