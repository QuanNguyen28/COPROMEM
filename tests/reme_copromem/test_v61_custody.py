from __future__ import annotations
import json
from pathlib import Path
from copromem.experiments.reme_copromem.v61_custody import classify

def test_public_inventory_and_withheld_mentions_are_not_exposure(tmp_path: Path):
    (tmp_path/"artifacts").mkdir(); (tmp_path/"research").mkdir()
    inventory=tmp_path/"artifacts"/"public-dev-descriptors.json"; inventory.write_text(json.dumps({"tasks":[{"task_id":"aaaaaaa_1"}]}))
    (tmp_path/"research"/"report.md").write_text("withheld bbbbbbb_1")
    result=classify(tmp_path,inventory)
    assert result["hard_exclusion"]==[]
    assert set(result["public_mention_only"])=={"aaaaaaa_1","bbbbbbb_1"}

def test_execution_and_ambiguous_records_fail_closed(tmp_path: Path):
    (tmp_path/"artifacts"/"evaluation").mkdir(parents=True); (tmp_path/"research").mkdir()
    inventory=tmp_path/"research"/"public-dev-descriptors.json"; inventory.write_text("{}")
    (tmp_path/"artifacts"/"evaluation"/"x.json").write_text(json.dumps({"task_id":"ccccccc_1","after_score":1.0,"history":[]}))
    (tmp_path/"artifacts"/"unknown.json").write_text(json.dumps({"task_id":"ddddddd_1", "note":"unknown custody"}))
    result=classify(tmp_path,inventory)
    assert "ccccccc_1" in result["hard_exclusion"]
    assert "ddddddd_1" in result["ambiguous_exclusion"]
