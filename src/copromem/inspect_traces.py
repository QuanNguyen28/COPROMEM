import json

with open('artifacts/live_browser_benchmark/benchmark_results_latest.json') as f:
    data = json.load(f)

for tid in [1, 3, 63, 64, 65]:
    t_copro = [t for t in data['arms_comparison']['copromem_v2']['tasks'] if t['task_id'] == tid]
    t_no_mem = [t for t in data['arms_comparison']['no_memory']['tasks'] if t['task_id'] == tid]
    t_sem = [t for t in data['arms_comparison']['semantic_rag']['tasks'] if t['task_id'] == tid]
    if t_copro:
        c = t_copro[0]
        n = t_no_mem[0] if t_no_mem else {}
        s = t_sem[0] if t_sem else {}
        print("=" * 70)
        print(f"=== TASK {tid}: {c['intent']} ===")
        print(f"  no_memory   : success={n.get('success')}, steps={n.get('steps')}, cost=${n.get('cost_usd', 0):.4f}")
        print(f"  semantic_rag: success={s.get('success')}, steps={s.get('steps')}, cost=${s.get('cost_usd', 0):.4f}")
        print(f"  copromem_v2 : success={c.get('success')}, steps={c.get('steps')}, cost=${c.get('cost_usd', 0):.4f}")
        print(f"  Injected memory in copromem:\n{c.get('injected_memory')}")
        print(f"  copromem actions ({len(c['actions_taken'])}):")
        for idx, act in enumerate(c['actions_taken'][:15]):
            print(f"    [{idx+1}] {act}")
        if len(c['actions_taken']) > 15:
            print(f"    ... [{len(c['actions_taken']) - 15} more actions]")
