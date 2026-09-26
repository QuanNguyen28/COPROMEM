"""Zero-cost direct-upstream ReMe audit; never falls back to local adapters."""
import importlib
import json
import sys
from pathlib import Path

root=Path("/home/xiqhq/copromem-reme")
if not root.exists(): raise SystemExit("pinned checkout absent")
sys.path.insert(0,str(root))
targets=["reme.extension.procedural_memory","test.cookbook.appworld"]
result={"checkout":str(root),"imports":{}}
for name in targets:
    try:
        module=importlib.import_module(name)
        result["imports"][name]={"status":"direct_upstream_imported","file":getattr(module,"__file__",None)}
    except Exception as exc:
        result["imports"][name]={"status":"unsupported_import","error_type":type(exc).__name__,"message":str(exc)[:300]}
print(json.dumps(result,sort_keys=True))
