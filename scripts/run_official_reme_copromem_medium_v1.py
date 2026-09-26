#!/usr/bin/env python3
"""Standalone medium_v1 coordinator, reusing immutable reduced_v2 acquisition."""
from __future__ import annotations
import json, os, pathlib, sys

ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN=ROOT/"artifacts/research/official_reme_copromem_pilot/medium_v1"
OLD=ROOT/"artifacts/research/official_reme_copromem_pilot/reduced_v2"
os.environ["OFFICIAL_PILOT_HARD_CAP"]="140"
os.environ["OFFICIAL_PILOT_RUN"]=str(RUN)
os.environ.setdefault("OFFICIAL_PILOT_C_FLOOR_GB", "5")
sys.path.insert(0,str(ROOT))
import scripts.run_official_reme_copromem_reduced_v2 as base
from research.official_pilot.locked_openrouter import AppendOnlyLedger

base.RUN=RUN; base.MANIFEST=RUN/"manifest.json"; base.PROGRESS=RUN/"progress.jsonl"
base.LEDGER=RUN/"successor-ledger.jsonl"; base.STATUS=RUN/"runner-status.json"

def immutable_acquisition(manifest, api_key, ledger):
    records=[]
    for item in manifest["acquisition_source"]["artifacts"]:
        path=ROOT/item["path"]
        if __import__("hashlib").sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise RuntimeError("immutable acquisition artifact hash mismatch")
        records.append(json.loads(path.read_text(encoding="utf-8")))
    if len(records)!=5: raise RuntimeError("expected five immutable acquisition artifacts")
    base.append(base.PROGRESS,{"event":"acquisition_reused_immutable","artifact_count":5,
        "replayed_acquisition":False})
    return records

base.acquisition=immutable_acquisition
def carry_forward_exposure():
    """Carry immutable prior exposure once so USD140 remains all-inclusive."""
    marker="carry-forward-reduced-v2-delta"
    if base.LEDGER.exists() and marker in base.LEDGER.read_text(encoding="utf-8"):
        return
    # The base preflight/carry record already accounts for USD0.03131748.
    # Add only the immutable remainder verified in reduced_v2 final report.
    delta=0.189716311-0.03131748
    ledger=AppendOnlyLedger(base.LEDGER,140.0)
    ledger.reserve(marker,delta,{"role":"immutable_historical_carry_forward","source":"reduced_v2_final_report"})
    ledger.settle(marker,delta,{"role":"immutable_historical_carry_forward","source":"reduced_v2_final_report"})
carry_forward_exposure()
amendment=RUN/"INFRASTRUCTURE_AMENDMENT_C_FLOOR_5GB.json"
if not amendment.exists():
    base.write_json(amendment,{"type":"infrastructure_only","change":"Windows C-drive safety floor: 10 GB to 5 GB",
        "scientific_parameters_unchanged":["manifest","task allocation","model route","memory state","scoring","analysis"],
        "reason":"resume after storage-floor stop"})
    base.append(base.PROGRESS,{"event":"infrastructure_amendment","name":"c_drive_floor_5gb",
        "previous_floor_gb":10,"new_floor_gb":5,"scientific_parameters_changed":False})
if __name__=="__main__": base.main()
