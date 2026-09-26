import ray
ray.init(num_cpus=1, include_dashboard=False, _temp_dir="/mnt/e/Project/AAMAS/reme-ray-tmp")
f=ray.remote(lambda: 7)
assert ray.get(f.remote())==7
ray.shutdown()
import sys
sys.path.insert(0,"/home/xiqhq/copromem-reme")
import benchmark.appworld.prompt
import benchmark.appworld.appworld_react_agent
import benchmark.appworld.run_appworld
print("RAY_REME_UPSTREAM_OK")
