import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("smoke_worker",Path("research/containers/appworld/smoke_worker.py"))
worker=importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
class World:
    def __init__(self): self.actions=[]
    def execute(self,a): self.actions.append(a); return {"ok":a}
    def score(self): return self.actions==["a","b"]
def test_fixture_persists_multiple_actions_and_scores():
    world=World(); result=worker.fixture(world,["a","b"])
    assert result["terminated"] and result["score"] and len(result["outputs"])==2
def test_dry_run_never_opens_payload():
    result=worker.dry_run(["50e1ac9_1","fac291d_1"],["50e1ac9_1","fac291d_1"])
    assert result["payload_opened"] is False
