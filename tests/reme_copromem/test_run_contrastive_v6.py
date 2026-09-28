import importlib.util
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('run_v6',Path(__file__).parents[2]/'scripts'/'run_contrastive_v6.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
def test_v6_selection_is_stable_and_execution_only_exclusions(monkeypatch):
 monkeypatch.setattr(MOD,'executed_ids',lambda:{'aaa0000_1'})
 monkeypatch.setattr(MOD,'INVENTORY',Path(__file__))
 assert MOD._norm('Send 12 to "Lee"')=='send <value> to <value>'
def test_v6_git_helper_accepts_windows_worktree_pointer(monkeypatch, tmp_path):
 monkeypatch.setattr(MOD,'ROOT',tmp_path)
 (tmp_path/'.git').write_text('gitdir: E:/Project/AAMAS/COPROMEM/.git/worktrees/COPROMEM-review\n')
 seen={}
 monkeypatch.setattr(MOD.subprocess,'check_output',lambda *_a,**kw: seen.update(kw.get('env',{})) or 'abc\n')
 assert MOD.git()=='abc' and seen['GIT_DIR'].startswith('/mnt/e/')
def test_v6_has_no_reme_or_v53_lifecycle():
 source=(Path(__file__).parents[2]/'scripts'/'run_contrastive_v6.py').read_text()
 assert 'task_boundary' not in source and 'reme_copromem.task_boundary' not in source
def test_v6_execution_evidence_configuration_has_worker_required_path():
 source=(Path(__file__).parents[2]/'scripts'/'run_contrastive_v6.py').read_text()
 assert "'registry_path':str(REGISTRY)" in source and "execution_evidence=evidence" in source
def test_v6_registry_projection_retains_frozen_callable_identity(tmp_path, monkeypatch):
 registry=tmp_path/'registry.json';registry.write_text('{"registry_sha256":"full","operations":[],"dependency_edges":[]}')
 monkeypatch.setattr(MOD,'REGISTRY',registry)
 assert MOD._registry()['registry_sha256']=='full'
def test_v6_cli_normalizes_run_path_before_worker_boundary(monkeypatch, tmp_path):
 seen=[]; monkeypatch.setattr(MOD,'prepare',lambda path:seen.append(path))
 monkeypatch.setattr(MOD.sys,'argv',['run_contrastive_v6.py','prepare','--run',str(tmp_path/'relative')])
 MOD.main(); assert seen[0].is_absolute()
