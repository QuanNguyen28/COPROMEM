import builtins
import contextlib
import io
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/public_presence.py")
)


def test_generic_name_selection_ignores_literal_values_and_api_attribute_names():
    assert MODULE["selected_names"](
        ["items = apis.anything.fetch(token=key)\nprint(items)\nmsg='secret_value'"]
    ) == ["items", "key", "msg"]


def test_presence_never_exports_values_or_invokes_object_methods_or_mutates_bindings():
    class Trap:
        def __repr__(self):
            raise AssertionError("must not format object")

        def __len__(self):
            raise AssertionError("must not call length")

    namespace = {
        "__builtins__": builtins.__dict__,
        "secret": "fixture-not-a-real-key",
        "opaque": Trap(),
    }
    original = {name: id(value) for name, value in namespace.items()}
    query = MODULE["construct"](
        {"programs": ["print(secret,opaque,absent)"], "prefix": []}
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(query["query"], namespace)  # noqa: S102 - execute only the generated fixture query
    assert "fixture-not-a-real-key" not in output.getvalue()
    assert {name: id(value) for name, value in namespace.items()} == original
    assert MODULE["parse_output"](output.getvalue(), query["names"])["bindings"] == [
        {"name": "absent", "present": False},
        {"name": "opaque", "present": True},
        {"name": "secret", "present": True},
    ]


@pytest.mark.parametrize(
    "prefix",
    [
        "print = replacement",
        "del NameError",
        "def print():\n    pass",
        "from json import loads as print",
        "try:\n    pass\nexcept Exception as NameError:\n    pass",
        "match x:\n    case {'x': print}:\n        pass",
    ],
)
def test_control_builtin_shadowing_is_rejected_before_query_execution(prefix):
    with pytest.raises(ValueError, match="shadow"):
        MODULE["construct"]({"programs": ["x"], "prefix": [prefix]})


def test_nonpublic_fields_and_policy_forbidden_selected_names_fail_closed():
    with pytest.raises(ValueError):
        MODULE["construct"]({"programs": ["x"], "prefix": [], "namespace": {"x": 1}})
    with pytest.raises(ValueError, match="introspection"):
        MODULE["construct"]({"programs": ["_private"], "prefix": []})


def test_empty_selection_has_its_own_exact_output():
    query = MODULE["construct"]({"programs": ["print(1)"], "prefix": []})
    assert query["names"] == []
    assert MODULE["parse_output"](MODULE["EMPTY"] + "\n", []) == {
        "version": MODULE["VERSION"],
        "bindings": [],
    }
    with pytest.raises(ValueError):
        MODULE["parse_output"]("", [])


@pytest.mark.parametrize(
    "output",
    [
        "",
        'COPROMEM_PRESENCE={"name":"x","present":1}',
        'COPROMEM_PRESENCE={"name":"y","present":true}',
        'COPROMEM_PRESENCE={"name":"x","present":true,"value":"secret"}',
        'COPROMEM_PRESENCE={"name":"x","present":true}\nCOPROMEM_PRESENCE={"name":"x","present":true}',
        "missing marker",
        "COPROMEM_PRESENCE={",
    ],
)
def test_invalid_extra_missing_or_malformed_outputs_are_not_observations(output):
    with pytest.raises(ValueError):
        MODULE["parse_output"](output, ["x"])


def test_duplicate_json_keys_and_out_of_order_names_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        MODULE["parse_output"](
            'COPROMEM_PRESENCE={"name":"x","present":false,"present":true}', ["x"]
        )
    with pytest.raises(ValueError):
        MODULE["parse_output"](
            'COPROMEM_PRESENCE={"name":"b","present":true}\nCOPROMEM_PRESENCE={"name":"a","present":true}',
            ["a", "b"],
        )


def test_oversized_name_registry_is_rejected_not_truncated():
    with pytest.raises(ValueError, match="bounded"):
        MODULE["construct"](
            {"programs": ["\n".join(f"variable_{i}" for i in range(300))], "prefix": []}
        )
