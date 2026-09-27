#!/usr/bin/env python3
"""List AppWorld split IDs only; this never opens task payloads."""
import argparse
from appworld import load_task_ids
p=argparse.ArgumentParser(); p.add_argument("split",nargs="?",default="test_normal")
for task_id in sorted(load_task_ids(p.parse_args().split)):
    print(task_id)
