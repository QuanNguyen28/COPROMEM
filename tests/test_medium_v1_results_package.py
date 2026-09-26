"""Offline integrity checks for the sanitized, reproducible medium_v1 package."""
from __future__ import annotations
import hashlib, json, pathlib, subprocess, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"research/medium_v1_results"
def test_medium_manifest_and_report_are_complete_and_sanitized():
    manifest=json.loads((OUT/"manifest.json").read_text())
    assert len(manifest["evaluation"]["task_ids"])==40
    assert manifest["evaluation"]["seeds"]==[9101,9102,9103,9104]
    assert manifest["budget"]["hard_cap_usd"]==140.0
    assert hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()==(OUT/"manifest.sha256").read_text().strip()
    report=json.loads((OUT/"final-report.json").read_text())
    assert report["completion"]=={"expected_evaluation_trajectories":640,"completed_evaluation_trajectories":640,"complete":True}
    assert report["budget"]["hard_cap_usd"]==140.0
    assert "reduced_v2" not in (OUT/"FINAL_REPORT.md").read_text()
def test_medium_report_generator_is_replayable_without_dispatch():
    result=subprocess.run([sys.executable,str(ROOT/"research/scripts/build_medium_v1_final_report.py")],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0, result.stderr

if __name__=="__main__":
    test_medium_manifest_and_report_are_complete_and_sanitized()
    test_medium_report_generator_is_replayable_without_dispatch()
    print("PASS medium_v1 results package")
