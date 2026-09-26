"""Import-only audit of pinned upstream ReMe AppWorld modules."""
import importlib, json, sys
from pathlib import Path
root=Path("/home/xiqhq/copromem-reme")
sys.path.insert(0,str(root))
names=["benchmark.appworld.prompt","benchmark.appworld.appworld_react_agent","benchmark.appworld.run_appworld"]
out={}
for name in names:
    try:
        m=importlib.import_module(name)
        out[name]={"status":"direct_upstream","file":m.__file__}
    except Exception as e:
        out[name]={"status":"failed","type":type(e).__name__,"message":str(e)[:300]}
print(json.dumps(out,sort_keys=True))
