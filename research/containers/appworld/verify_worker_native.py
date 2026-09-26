"""Run the worker's sole authorized native fixture."""
import json
from smoke_worker import native_fixture
print(json.dumps(native_fixture(), sort_keys=True))
