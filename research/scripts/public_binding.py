"""Research-only public-code transplant binding, not a sound Python verifier."""

from __future__ import annotations

import ast
import builtins
import copy
from collections import defaultdict

from copromem.checkpoints import digest
from copromem.procedural_diff import BlockTransplant, ast_identity, parse_program

VERSION = "public-api-keyword-input-binding-output-closure-v1"
BUILTINS = frozenset(dir(builtins)) | {"apis"}


def loaded(node: ast.AST) -> set[str]:
    return {
        item.id
        for item in ast.walk(node)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
    }


def bound(nodes: list[ast.stmt]) -> set[str]:
    names = set()
    for statement in nodes:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update(
                    alias.asname or alias.name.split(".")[0] for alias in node.names
                )
    return names


def sequence_io(nodes: list[ast.stmt]) -> tuple[set[str], set[str]]:
    """Conservative normal-completion branch bindings; calls may still fail."""
    required, defined = set(), set()
    for node in nodes:
        reads, writes = statement_io(node)
        required |= reads - defined
        defined |= writes
    return required, defined


def statement_io(node: ast.stmt) -> tuple[set[str], set[str]]:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        reads = loaded(node.value) if node.value is not None else set()
        reads |= set().union(*(loaded(target) for target in targets))
        return reads, bound([node]) if node.value is not None else set()
    if isinstance(node, ast.AugAssign):
        return loaded(node) | bound([node]), bound([node])
    if isinstance(node, (ast.Expr, ast.Assert, ast.Raise)):
        return loaded(node), set()
    if isinstance(node, (ast.Pass, ast.Break, ast.Continue)):
        return set(), set()
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return set(), bound([node])
    if isinstance(node, ast.If):
        left_reads, left_defs = sequence_io(node.body)
        right_reads, right_defs = sequence_io(node.orelse)
        return loaded(node.test) | left_reads | right_reads, left_defs & right_defs
    if isinstance(node, (ast.For, ast.While)):
        body_reads, _ = sequence_io(node.body)
        else_reads, _ = sequence_io(node.orelse)
        if isinstance(node, ast.For):
            loop_names = {
                item.id
                for item in ast.walk(node.target)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
            }
            return loaded(node.iter) | (body_reads - loop_names) | else_reads, set()
        return loaded(node.test) | body_reads | else_reads, set()
    if isinstance(node, ast.Try):
        body_reads, body_defs = sequence_io(node.body)
        normal_reads, normal_defs = sequence_io(node.orelse)
        reads = body_reads | (normal_reads - body_defs)
        definitions = body_defs | normal_defs
        for handler in node.handlers:
            handler_reads, handler_defs = sequence_io(handler.body)
            reads |= (handler_reads - {handler.name}) | (
                loaded(handler.type) if handler.type is not None else set()
            )
            definitions &= handler_defs
        final_reads, final_defs = sequence_io(node.finalbody)
        return reads | (final_reads - definitions), definitions | final_defs
    raise ValueError("unsupported binding-analysis statement: " + type(node).__name__)


def api_path(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return (
        ".".join(["apis", *reversed(parts)])
        if isinstance(node, ast.Name) and node.id == "apis" and parts
        else None
    )


def infer_mapping(
    target: list[ast.stmt], inserted: list[ast.stmt], external: set[str]
) -> tuple[dict[str, str], list[dict]]:
    target_arguments = defaultdict(set)
    dynamic_keyword_paths = set()
    target_tree = ast.Module(body=target, type_ignores=[])
    for node in ast.walk(target_tree):
        if isinstance(node, ast.Call) and (path := api_path(node.func)):
            for keyword in node.keywords:
                if keyword.arg is None:
                    dynamic_keyword_paths.add(path)
                else:
                    target_arguments[(path, keyword.arg)].add(
                        keyword.value.id
                        if isinstance(keyword.value, ast.Name)
                        else None
                    )
    matches = defaultdict(set)
    for node in ast.walk(ast.Module(body=inserted, type_ignores=[])):
        if isinstance(node, ast.Call) and (path := api_path(node.func)):
            for keyword in node.keywords:
                if (
                    isinstance(keyword.value, ast.Name)
                    and keyword.value.id in external
                    and keyword.arg is not None
                ):
                    matches[keyword.value.id] |= target_arguments[(path, keyword.arg)]
                    if path in dynamic_keyword_paths:
                        matches[keyword.value.id].add(None)
    mapping, rejected = {}, []
    local_names = bound(inserted)
    for donor_name, options in sorted(matches.items()):
        if not options:
            continue
        if len(options) != 1 or None in options:
            rejected.append(
                {
                    "reason": "ambiguous_or_nonidentifier_api_argument",
                    "donor_name": donor_name,
                    "target_identifiers": sorted(
                        name for name in options if name is not None
                    ),
                    "has_nonidentifier": None in options,
                }
            )
        else:
            target_name = next(iter(options))
            if target_name in local_names and target_name != donor_name:
                rejected.append(
                    {
                        "reason": "mapping_would_capture_donor_local",
                        "donor_name": donor_name,
                        "target_name": target_name,
                    }
                )
            else:
                mapping[donor_name] = target_name
    return mapping, rejected


class RenameInputs(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
            return ast.copy_location(
                ast.Name(id=self.mapping[node.id], ctx=ast.Load()), node
            )
        return node


def bind_transplant(edit: BlockTransplant, public_prefix: list[str]) -> dict:
    """No score, task identifier, hidden namespace or credential-value input."""
    if type(public_prefix) is not list or any(
        not isinstance(code, str) for code in public_prefix
    ):
        raise TypeError("public prefix must contain only source-code strings")
    old = edit.record()
    origin, donor = (
        parse_program(edit.failed_program),
        parse_program(edit.successful_program),
    )
    start, stop = edit.origin_span
    inserted = [
        copy.deepcopy(donor.body[index]) for index in edit.retained_donor_indices
    ]
    before, after = origin.body[:start], origin.body[stop:]
    result = {
        "operator": VERSION,
        "original_proposal_digest": digest(old),
        "public_prefix_digest": digest(public_prefix),
        "status": "rejected",
        "mapping": {},
        "preserved_setup_indices": [],
        "rejections": [],
        "required_inputs": [],
        "missing_inputs": [],
        "required_outputs": [],
        "missing_outputs": [],
        "program": None,
        "program_ast_digest": None,
        "changed_from_original_proposal": False,
        "limitation": "Bounded public-code construction check, not semantic equivalence, runtime definite-assignment proof, learned scope or admission. Source-prefix calls may have failed; aliases, mutation and abrupt control flow are not proved.",
    }
    try:
        required, _ = sequence_io(inserted)
        # Names assigned anywhere in the donor block are not external rename
        # targets, even when their control-flow availability is uncertain.
        external = required - bound(inserted) - BUILTINS
        mapping, rejected = infer_mapping(origin.body, inserted, external)
        result["mapping"], result["rejections"] = mapping, rejected
        inserted = [RenameInputs(mapping).visit(node) for node in inserted]
        required, block_definitions = sequence_io(inserted)
        required -= BUILTINS
        result["required_inputs"] = sorted(required)
        prefix_definitions = set()
        for program in public_prefix:
            _, definitions = sequence_io(parse_program(program).body)
            prefix_definitions |= definitions
        _, local_prefix_definitions = sequence_io(before)
        prefix_definitions |= local_prefix_definitions
        setup = []
        # Preserve the target's value at this boundary, even when an earlier
        # action happened to bind the same name. Never read its harness value.
        for name in sorted(set(mapping.values())):
            positions = [
                index
                for index in range(start, stop)
                if name in bound([origin.body[index]])
            ]
            if not positions:
                continue
            statement = origin.body[positions[0]]
            if (
                len(positions) != 1
                or not isinstance(statement, ast.Assign)
                or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name)
                or statement.targets[0].id != name
                or not isinstance(statement.value, ast.Constant)
            ):
                result["rejections"].append(
                    {
                        "reason": "mapped_target_setup_not_unique_literal_assignment",
                        "target_name": name,
                        "original_indices": positions,
                    }
                )
                continue
            setup.append(positions[0])
        setup = sorted(set(setup))
        result["preserved_setup_indices"] = setup
        setup_nodes = [copy.deepcopy(origin.body[index]) for index in setup]
        _, setup_definitions = sequence_io(setup_nodes)
        result["missing_inputs"] = sorted(
            required - prefix_definitions - setup_definitions
        )
        suffix_requirements, _ = sequence_io(after)
        required_outputs = bound(origin.body[start:stop]) & suffix_requirements
        result["required_outputs"] = sorted(required_outputs)
        result["missing_outputs"] = sorted(
            required_outputs
            - prefix_definitions
            - setup_definitions
            - block_definitions
        )
        if result["missing_inputs"]:
            result["rejections"].append(
                {
                    "reason": "unclosed_external_inputs",
                    "names": result["missing_inputs"],
                }
            )
        if result["missing_outputs"]:
            result["rejections"].append(
                {
                    "reason": "lost_required_target_outputs",
                    "names": result["missing_outputs"],
                }
            )
        rendered = (
            ast.unparse(
                ast.Module(
                    body=[*before, *setup_nodes, *inserted, *after], type_ignores=[]
                )
            )
            + "\n"
        )
        observed = parse_program(rendered)
        suffix_start = len(before) + len(setup_nodes) + len(inserted)
        if [ast_identity(node) for node in observed.body[: len(before)]] != [
            ast_identity(node) for node in before
        ] or [ast_identity(node) for node in observed.body[suffix_start:]] != [
            ast_identity(node) for node in after
        ]:
            raise ValueError("untouched target prefix/suffix AST changed")
        result.update(
            program=rendered,
            program_ast_digest=digest(ast_identity(observed)),
            preserved_prefix_ast_digest=digest([ast_identity(node) for node in before]),
            preserved_suffix_ast_digest=digest([ast_identity(node) for node in after]),
        )
        result["changed_from_original_proposal"] = (
            result["program_ast_digest"] != old["program_ast_digest"]
        )
        if not result["rejections"]:
            result["status"] = (
                "accepted_changed"
                if result["changed_from_original_proposal"]
                else "accepted_unchanged"
            )
    except (SyntaxError, ValueError) as exc:
        result["rejections"].append(
            {
                "reason": "unsupported_or_invalid_binding_syntax",
                "error_type": type(exc).__name__,
                "detail": str(exc),
            }
        )
    return result
