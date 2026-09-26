import json, subprocess, sys
p=subprocess.Popen([sys.executable,"/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def send(x):
 p.stdin.write(json.dumps(x)+"\n");p.stdin.flush();return json.loads(p.stdout.readline())
start=send({"op":"start","task_id":"82e2fac_1","experiment_name":"worker_protocol_fixture","fixture":True})
send({"op":"action","code":"protocol_counter = 1"})
send({"op":"action","code":"protocol_counter = protocol_counter + 1"})
# Uses public fixture test logic only; no model call.
finish=send({"op":"finish","fixture_solution":True})
print(json.dumps({"started":start["ok"],"finished":finish}))
assert start["ok"] and finish["pass_count"]==2 and finish["fail_count"]==0
