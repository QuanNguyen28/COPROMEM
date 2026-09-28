import importlib.util
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('run_v6',Path(__file__).parents[2]/'scripts'/'run_contrastive_v6.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
def test_v6_selection_is_stable_and_execution_only_exclusions(monkeypatch):
 monkeypatch.setattr(MOD,'executed_ids',lambda:{'aaa0000_1'})
 monkeypatch.setattr(MOD,'INVENTORY',Path(__file__))
 assert MOD._norm('Send 12 to "Lee"')=='send <value> to <value>'
def test_v6_has_no_reme_or_v53_lifecycle():
 source=(Path(__file__).parents[2]/'scripts'/'run_contrastive_v6.py').read_text()
 assert 'ReMe' not in source and 'task_boundary' not in source and 'embedding' not in source
