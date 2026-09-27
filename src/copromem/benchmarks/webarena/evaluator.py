"""WebArena official StringEvaluator ported directly from ReasoningBank evaluation harness.

Evaluates text answers against ground-truth reference answers without requiring
a full browser or CDPSession. Supports exact_match, must_include (with |OR| branches),
and fuzzy_match for N/A / non-existent target checks.
"""

from __future__ import annotations

import re
from typing import Any


class WebArenaStringEvaluator:
    """Evaluates agent's predicted answer string against WebArena reference answers."""

    @staticmethod
    def clean_answer(answer: str) -> str:
        """Strip enclosing quotes, lower-case, and normalize whitespace."""
        if not answer:
            return ""
        ans = str(answer).strip()
        if (ans.startswith("'") and ans.endswith("'")) or (ans.startswith('"') and ans.endswith('"')):
            ans = ans[1:-1]
        return ans.lower().strip()

    @classmethod
    def exact_match(cls, ref: str, pred: str) -> float:
        """Check if cleaned prediction exactly matches cleaned reference."""
        return float(cls.clean_answer(pred) == cls.clean_answer(ref))

    @classmethod
    def must_include(cls, ref: str, pred: str, tokenize: bool = False) -> float:
        """Check if reference phrase is included in prediction, optionally with token boundary."""
        clean_ref = cls.clean_answer(ref)
        clean_pred = cls.clean_answer(pred)
        if not clean_ref:
            return 1.0

        if tokenize and len(clean_ref) <= 2:
            tokens = re.findall(r"\b\w+\b", clean_pred)
            return float(clean_ref in tokens)
        return float(clean_ref in clean_pred)

    @classmethod
    def evaluate(
        cls,
        pred_answer: str,
        eval_spec: dict[str, Any] | None,
        intent: str = "",
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate prediction against eval_spec reference_answers.

        Returns:
            (success: bool, details: dict containing scores and per-approach checks)
        """
        if not eval_spec:
            return False, {"score": 0.0, "reason": "empty_eval_spec"}

        ref_answers = eval_spec.get("reference_answers") or {}
        ref_url = eval_spec.get("reference_url") or ""

        program_html = eval_spec.get("program_html") or []
        if not ref_answers and not ref_url and not program_html:
            return False, {"score": 0.0, "reason": "empty_eval_spec"}

        clean_pred = cls.clean_answer(pred_answer)
        score = 1.0
        checks: list[dict[str, Any]] = []

        if not ref_answers and not ref_url and program_html:
            # HTMLContentEvaluator equivalent: evaluate against required_contents
            ph_score = 1.0
            for target in program_html:
                req_contents = target.get("required_contents") or {}
                if "exact_match" in req_contents:
                    val = str(req_contents["exact_match"])
                    s = cls.exact_match(ref=val, pred=clean_pred)
                    checks.append({"type": "program_html_exact", "ref": val, "pred": pred_answer, "score": s})
                    ph_score *= s
                elif "must_include" in req_contents:
                    items = req_contents["must_include"]
                    if isinstance(items, list):
                        for item in items:
                            s = cls.must_include(ref=str(item), pred=clean_pred, tokenize=False)
                            checks.append({"type": "program_html_must_include", "ref": item, "pred": pred_answer, "score": s})
                            ph_score *= s
                    else:
                        s = cls.must_include(ref=str(items), pred=clean_pred, tokenize=False)
                        checks.append({"type": "program_html_must_include", "ref": items, "pred": pred_answer, "score": s})
                        ph_score *= s
            success = (ph_score >= 0.99)
            return success, {"score": ph_score, "checks": checks}

        if ref_url and not ref_answers:
            # url_match task (e.g. check out todos, recent issues)
            url_targets = [u.strip() for u in str(ref_url).split(" |OR| ")]
            url_matched = False
            for target in url_targets:
                path_part = target.split("__")[-1].lstrip("/").lower()
                if path_part and path_part in clean_pred:
                    url_matched = True
                    break
            score = 1.0 if url_matched else 0.0
            checks.append({"type": "url_match", "ref": ref_url, "pred": pred_answer, "score": score})
            return (score >= 0.99), {"score": score, "checks": checks}

        for approach, value in ref_answers.items():
            if approach == "exact_match":
                s = cls.exact_match(ref=str(value), pred=clean_pred)
                checks.append({"type": "exact_match", "ref": value, "pred": pred_answer, "score": s})
                score *= s

            elif approach == "must_include":
                items = value if isinstance(value, list) else [str(value)]
                for must_val in items:
                    or_choices = [c.strip() for c in str(must_val).split(" |OR| ")]
                    if len(or_choices) > 1:
                        s = max(cls.must_include(ref=c, pred=clean_pred, tokenize=False) for c in or_choices)
                    else:
                        s = cls.must_include(ref=str(must_val), pred=clean_pred, tokenize=(len(items) == 1))
                    checks.append({"type": "must_include", "ref": must_val, "pred": pred_answer, "score": s})
                    score *= s

            elif approach == "fuzzy_match":
                if str(value).strip() == "N/A":
                    na_patterns = (
                        r"\bn/a\b", r"\bnone\b", r"\bnot found\b", r"\bdoes not exist\b",
                        r"\bcannot find\b", r"\bno review\b", r"\bno reviews\b",
                        r"\b0\b", r"\bzero\b", r"\bnothing\b", r"\bno such\b"
                    )
                    is_na = (clean_pred == "n/a") or any(re.search(pat, clean_pred) for pat in na_patterns)
                    s = 1.0 if is_na else 0.0
                    checks.append({"type": "fuzzy_match_na", "ref": value, "pred": pred_answer, "score": s})
                    score *= s
                else:
                    ref_list = value if isinstance(value, list) else [str(value)]
                    s = max(cls.must_include(ref=str(r), pred=clean_pred) for r in ref_list)
                    checks.append({"type": "fuzzy_match", "ref": value, "pred": pred_answer, "score": s})
                    score *= s

        success = (score >= 0.99)
        return success, {"score": score, "checks": checks}
