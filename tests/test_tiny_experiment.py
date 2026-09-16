from copromem.tiny_experiment import learn_success_only_fields, run_tiny_experiment
from copromem.types import RunMode


def test_success_only_memory_reads_no_failed_trajectory_fields() -> None:
    class ExplodingFailure:
        success = False

        @property
        def plan(self):
            raise AssertionError("failure trajectory must not be read")

    assert learn_success_only_fields([ExplodingFailure()]) == ()


def test_tiny_three_arm_pipeline_smoke() -> None:
    report = run_tiny_experiment(seed=7)
    assert set(report["arms"]) == {
        RunMode.NO_MEMORY.value,
        RunMode.SUCCESS_ONLY_MEMORY.value,
        RunMode.CONTRACT_CHECK.value,
    }
    assert report["protocol"]["task_count"] == 6
    assert report["copromem"]["admitted_contract_count"] == 1
    assert report["claim_supported_in_this_run"] is True
    assert report["paired_copromem_vs_success_only"]["harmful_flips"] == 0
