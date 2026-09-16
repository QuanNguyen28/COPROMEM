"""Evidence-derived, name-based statement transplants; not admitted contracts.

This is a bounded proposal heuristic, not a sound Python slicer. Alias effects,
argument mutation, dynamic dispatch and arbitrary control dependence are not
proved by the syntax analysis. Every proposal requires independent effect tests.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace

from .checkpoints import digest

VERSION = "common-binding-backward-block-v1"
UNSUPPORTED = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.Global,
    ast.Nonlocal,
    ast.NamedExpr,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
)


def parse_program(program: str) -> ast.Module:
    tree = ast.parse(program)
    unsupported = sorted(
        {
            type(node).__name__
            for node in ast.walk(tree)
            if isinstance(node, UNSUPPORTED)
        }
    )
    if unsupported:
        raise ValueError("unsupported lexical scope: " + ", ".join(unsupported))
    return tree


def ast_identity(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def name_effects(statement: ast.stmt) -> tuple[set[str], set[str]]:
    """Conservative method-receiver mutation, with explicitly incomplete aliases."""
    reads, writes = set(), set()
    for node in ast.walk(statement):
        if isinstance(node, ast.Name):
            (reads if isinstance(node.ctx, ast.Load) else writes).add(node.id)
        elif isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            name = root_name(node)
            if name is not None:
                writes.add(name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = root_name(node.func.value)
            if name is not None:
                writes.add(name)
        elif isinstance(node, ast.AugAssign):
            name = root_name(node.target)
            if name is not None:
                reads.add(name)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            writes.add(node.name)
    return reads, writes


def anchors(tree: ast.Module) -> dict[str, int]:
    found = defaultdict(list)
    for index, statement in enumerate(tree.body):
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            found[statement.targets[0].id].append(index)
    return {name: indices[0] for name, indices in found.items() if len(indices) == 1}


def common_prefix(first: ast.Module, second: ast.Module) -> int:
    count = 0
    for left, right in zip(first.body, second.body):
        if ast_identity(left) != ast_identity(right):
            break
        count += 1
    return count


def producer_span(
    tree: ast.Module, anchor: str, index: int, prefix: int
) -> tuple[int, int]:
    last = index
    for position in range(index + 1, len(tree.body)):
        reads, writes = name_effects(tree.body[position])
        if anchor in writes:
            last = position
        elif anchor in reads:
            break  # Stop at the first non-mutating consumer of this binding.
    needed, selected = {anchor}, []
    for position in range(last, min(index, prefix) - 1, -1):
        reads, writes = name_effects(tree.body[position])
        if position == last or writes & needed:
            selected.append(position)
            needed = (needed - writes) | reads
    return min(selected), last + 1


def node_count(nodes: list[ast.stmt]) -> int:
    return sum(
        not isinstance(node, ast.expr_context)
        for statement in nodes
        for node in ast.walk(statement)
    )


@dataclass(frozen=True)
class BlockTransplant:
    failed_program: str
    successful_program: str
    anchor: str
    origin_span: tuple[int, int]
    donor_span: tuple[int, int]
    retained_donor_indices: tuple[int, ...]

    def __post_init__(self):
        origin = parse_program(self.failed_program)
        donor = parse_program(self.successful_program)
        for span, size in (
            (self.origin_span, len(origin.body)),
            (self.donor_span, len(donor.body)),
        ):
            if (
                len(span) != 2
                or any(type(value) is not int for value in span)
                or not 0 <= span[0] < span[1] <= size
            ):
                raise ValueError("invalid statement span")
        indices = self.retained_donor_indices
        if tuple(sorted(set(indices))) != indices or any(
            type(index) is not int
            or not self.donor_span[0] <= index < self.donor_span[1]
            for index in indices
        ):
            raise ValueError(
                "donor indices must be ordered, unique and inside the donor span"
            )

    def program(self) -> str:
        origin = parse_program(self.failed_program)
        donor = parse_program(self.successful_program)
        start, stop = self.origin_span
        body = (
            origin.body[:start]
            + [donor.body[index] for index in self.retained_donor_indices]
            + origin.body[stop:]
        )
        rendered = ast.unparse(ast.Module(body=body, type_ignores=[])) + "\n"
        observed = parse_program(rendered)
        if [ast_identity(node) for node in observed.body] != [
            ast_identity(node) for node in body
        ]:
            raise ValueError("rendered transplant changed AST semantics")
        return rendered

    def without(self, donor_index: int) -> BlockTransplant:
        if donor_index not in self.retained_donor_indices:
            raise ValueError("statement is not retained in this edit")
        return replace(
            self,
            retained_donor_indices=tuple(
                index for index in self.retained_donor_indices if index != donor_index
            ),
        )

    def record(self) -> dict:
        origin, donor = (
            parse_program(self.failed_program),
            parse_program(self.successful_program),
        )
        start, stop = self.origin_span
        inserted = [donor.body[index] for index in self.retained_donor_indices]
        program = self.program()
        return {
            "operator": VERSION,
            "anchor": self.anchor,
            "failed_program_digest": digest(self.failed_program),
            "successful_program_digest": digest(self.successful_program),
            "origin_span": list(self.origin_span),
            "donor_span": list(self.donor_span),
            "retained_donor_indices": list(self.retained_donor_indices),
            "program": program,
            "program_ast_digest": digest(ast_identity(parse_program(program))),
            "removed_statements": stop - start,
            "inserted_statements": len(inserted),
            "removed_ast_nodes": node_count(origin.body[start:stop]),
            "inserted_ast_nodes": node_count(inserted),
            "preserved_prefix_ast_digest": digest(
                [ast_identity(node) for node in origin.body[:start]]
            ),
            "preserved_suffix_ast_digest": digest(
                [ast_identity(node) for node in origin.body[stop:]]
            ),
            "status": "unvalidated local program proposal; no learned scope or contract admission",
        }


def propose_transplants(
    failed: str, successful: str
) -> tuple[list[BlockTransplant], list[dict]]:
    origin, donor = parse_program(failed), parse_program(successful)
    left, right = anchors(origin), anchors(donor)
    prefix = common_prefix(origin, donor)
    proposals, rejections, seen = [], [], set()
    for anchor in sorted(left.keys() & right.keys()):
        origin_span = producer_span(origin, anchor, left[anchor], prefix)
        donor_span = producer_span(donor, anchor, right[anchor], prefix)
        if [ast_identity(node) for node in origin.body[slice(*origin_span)]] == [
            ast_identity(node) for node in donor.body[slice(*donor_span)]
        ]:
            rejections.append({"anchor": anchor, "reason": "identical producer blocks"})
            continue
        edit = BlockTransplant(
            failed,
            successful,
            anchor,
            origin_span,
            donor_span,
            tuple(range(*donor_span)),
        )
        try:
            key = edit.record()["program_ast_digest"]
        except (SyntaxError, ValueError) as exc:
            rejections.append(
                {
                    "anchor": anchor,
                    "reason": "invalid transplant",
                    "error_type": type(exc).__name__,
                }
            )
            continue
        if key in seen:
            rejections.append(
                {"anchor": anchor, "reason": "duplicate proposed program AST"}
            )
            continue
        seen.add(key)
        proposals.append(edit)
    return proposals, rejections


def reduce_transplants(
    proposals: list[BlockTransplant],
    evaluate: Callable[[BlockTransplant], bool],
    *,
    max_variants: int,
) -> dict:
    """Budgeted, deterministic single-top-level-statement deletion search.

    The callback, not this syntax module, must establish the complete native
    effect gate. Cached ASTs avoid duplicate executions, not new task evidence.
    """
    if type(max_variants) is not int or max_variants < 1:
        raise ValueError("positive integer variant budget required")
    cache, decisions, retained = {}, [], []
    untested_initial = []

    def check(edit):
        key = edit.record()["program_ast_digest"]
        if key not in cache:
            if len(cache) >= max_variants:
                return None
            outcome = evaluate(edit)
            if type(outcome) is not bool:
                raise TypeError("effect evaluator must return a boolean")
            cache[key] = outcome
        return cache[key]

    for initial in proposals:
        outcome = check(initial)
        if outcome is None:
            untested_initial.append(initial.record())
            continue
        if not outcome:
            decisions.append(
                {
                    "kind": "initial",
                    "program_ast_digest": initial.record()["program_ast_digest"],
                    "passed": False,
                }
            )
            continue
        current, fixed_point = initial, False
        while True:
            accepted, incomplete = False, False
            for index in current.retained_donor_indices:
                trial = current.without(index)
                passed = check(trial)
                decisions.append(
                    {
                        "kind": "deletion",
                        "parent_program_ast_digest": current.record()[
                            "program_ast_digest"
                        ],
                        "removed_donor_index": index,
                        "trial_program_ast_digest": trial.record()[
                            "program_ast_digest"
                        ],
                        "passed": passed,
                        "not_executed_due_to_budget": passed is None,
                    }
                )
                if passed is None:
                    incomplete = True
                    break
                if passed:
                    current, accepted = trial, True
                    break
            if incomplete:
                break
            if not accepted:
                fixed_point = True
                break
        retained.append(
            {
                "initial": initial.record(),
                "retained": current.record(),
                "single_top_level_deletion_fixed_point": fixed_point,
                "global_minimality_claim": False,
            }
        )
    return {
        "tested_programs": cache,
        "tested_variant_count": len(cache),
        "decisions": decisions,
        "retained_edits": retained,
        "untested_initial_proposals": untested_initial,
        "search_complete": not untested_initial
        and all(row["single_top_level_deletion_fixed_point"] for row in retained),
    }
