"""CoProMem: executable procedural contracts at multi-agent handoffs."""

from .bank import ContractBank
from .contracts import Contract, contract_from_failure
from .workflow import WorkflowEngine
from .learning import ActionObservation, LearningCore, ReplayEvaluator, ReplayOutcome, ValidationTask

__all__ = [
    "ActionObservation", "Contract", "ContractBank", "LearningCore", "ReplayEvaluator",
    "ReplayOutcome", "ValidationTask", "WorkflowEngine", "contract_from_failure",
]
