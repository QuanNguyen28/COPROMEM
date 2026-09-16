"""Fallible build-only retry notes; never admitted procedural contracts."""

from __future__ import annotations

from .checkpoints import (
    GenerationService,
    IntegrityError,
    RunStore,
    canonical,
    digest,
    matched_seed,
)
from .stateful_source import PUBLIC_ONBOARDING_V2, prompt_context, transport_price_caps

REFLECTION_SYSTEM = (
    """You are preparing one further BUILD/TRAINING attempt by the same fixed planner/executor team. You receive exactly one prior public task trajectory and its binary final success flag. Inspect observed actions, public errors and task requirements. Return a concise practical note for the next fresh attempt: what to preserve, what to change, and which uncertain facts or API signatures must be verified. Use only the supplied evidence and public interface guidance. Do not invent hidden test results, diagnoses, data, people, API signatures, or success guarantees. Do not merely copy the previous final answer or simulated credentials: fresh execution must discover needed values. The note is fallible textual reflection, not an executable verifier or learned contract. Return plain text, at most a short paragraph or a few actionable points.\n"""
    + PUBLIC_ONBOARDING_V2
)


def reflection_input(frame: dict, native_success: bool, settings: dict) -> dict:
    if type(native_success) is not bool:
        raise ValueError("only a binary native outcome is permitted")
    wrapper = {"previous_attempt": {}, "previous_native_success": native_success}
    cap = settings["reflection_context_chars"]
    wrapper["previous_attempt"] = prompt_context(
        frame,
        cap - len(canonical(wrapper)),
        output_chars=settings["history_output_chars"],
        program_chars=settings["history_program_chars"],
    )
    if len(canonical(wrapper)) > cap:
        raise IntegrityError("reflection input exceeds its registered cap")
    return wrapper


def note_from_call(
    task_id: str, source_episode_id: str, call_id: str, text: str, max_chars: int
) -> dict:
    if type(max_chars) is not int or max_chars < 1 or not isinstance(text, str):
        raise ValueError("invalid note or text cap")
    return {
        "task_id": task_id,
        "source_episode_id": source_episode_id,
        "reflection_call_id": call_id,
        "lesson": text[:max_chars],
        "truncated": len(text) > max_chars,
        "status": "Fallible build-only retry note; not an admitted contract or verified instruction.",
    }


def create_note(
    service: GenerationService, store: RunStore, settings: dict, source: dict
) -> dict:
    task_id = source["task_id"]
    generation = service.call(
        REFLECTION_SYSTEM,
        canonical(source["reflection_input"]),
        settings["reflection_tokens"],
        matched_seed(settings["seed"], task_id, "build-reflection", 0),
    )
    note = note_from_call(
        task_id,
        source["episode_id"],
        generation.request_id,
        generation.text,
        settings["reflection_note_chars"],
    )
    store.write("source_retry_notes", task_id, note)
    return note


def retry_settings(protocol: dict, store: RunStore, task_id: str) -> dict:
    """Reconstruct the only permitted context extension from its recorded call."""
    if protocol["context_version"] != "public-history-retry-v3":
        raise ValueError("retry notes require the registered source context version")
    source = store.read("reflection_sources", task_id)
    note = store.read("source_retry_notes", task_id)
    if source is None or note is None or source["task_id"] != task_id:
        raise IntegrityError("missing or mismatched registered retry source/note")
    bindings = store.read("reflection_allocation", "sources")
    if bindings is None or bindings["sources"].get(task_id) != digest(source):
        raise IntegrityError("reflection source differs from frozen allocation")
    call = store.read("calls", note["reflection_call_id"])
    if (
        call is None
        or digest(call["request"]) != note["reflection_call_id"]
        or digest(call["response"]) != call["response_sha256"]
    ):
        raise IntegrityError("reflection generation digest mismatch")
    request = call["request"]
    prices = transport_price_caps(protocol)
    expected_provider = {
        "provider": protocol["provider"],
        "allow_fallbacks": False,
        "max_prompt_price_per_million": prices["prompt_price_per_million"],
        "max_completion_price_per_million": prices["completion_price_per_million"],
    }
    if (
        request["namespace"] != protocol["cycle_id"]
        or request["model"] != protocol["model"]
        or request["temperature"] != 0
        or request["provider_configuration"] != expected_provider
        or request["system"] != REFLECTION_SYSTEM
        or request["user"] != canonical(source["reflection_input"])
        or request["max_tokens"] != protocol["reflection_tokens"]
        or request["seed"]
        != matched_seed(protocol["seed"], task_id, "build-reflection", 0)
        or note
        != note_from_call(
            task_id,
            source["episode_id"],
            note["reflection_call_id"],
            call["response"]["text"],
            protocol["reflection_note_chars"],
        )
    ):
        raise IntegrityError("reflection source/request/note binding mismatch")
    return {**protocol, "source_retry_note": note}
