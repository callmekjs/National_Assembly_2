import sys
from pathlib import Path
sys.path.insert(0, r'C:\National_Assembly_2')

from service.etl.loader.jsonl_to_postgres_v2 import load_qa_pairs

# Test with a nonexistent path
result = load_qa_pairs(Path("/nonexistent/qa_pairs_v2.jsonl"))
print(f"Result for missing file: {result}")
print(f"Expected: True (skip, not error)")
