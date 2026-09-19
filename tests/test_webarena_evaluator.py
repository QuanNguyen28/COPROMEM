"""Unit tests for WebArenaStringEvaluator ported from ReasoningBank."""

from copromem.webarena_evaluator import WebArenaStringEvaluator


def test_exact_match_evaluator():
    eval_spec = {
        "eval_types": ["string_match"],
        "reference_answers": {"exact_match": "Quest Lumaflex™ Band"},
    }
    # Exact match (case insensitive)
    ok, details = WebArenaStringEvaluator.evaluate("Quest Lumaflex™ Band", eval_spec)
    assert ok is True
    assert details["score"] == 1.0

    ok_case, _ = WebArenaStringEvaluator.evaluate("quest lumaflex™ band", eval_spec)
    assert ok_case is True

    # Wrong product
    fail, details_fail = WebArenaStringEvaluator.evaluate("Sprite Stasis Ball", eval_spec)
    assert fail is False
    assert details_fail["score"] == 0.0


def test_must_include_evaluator():
    eval_spec = {
        "eval_types": ["string_match"],
        "reference_answers": {
            "must_include": [
                "Joseph Brzezinski",
                "Catso",
                "Dibbins",
                "Anglebert Dinkherhump",
                "Michelle Davis",
            ]
        },
    }
    pred_all = (
        "The reviewers mentioning ear cups are Joseph Brzezinski, Catso, Dibbins, "
        "Anglebert Dinkherhump, and Michelle Davis."
    )
    ok, details = WebArenaStringEvaluator.evaluate(pred_all, eval_spec)
    assert ok is True
    assert details["score"] == 1.0

    # Missing one reviewer
    pred_missing = "Reviewers: Joseph Brzezinski, Catso, Dibbins, Anglebert Dinkherhump."
    fail, details_fail = WebArenaStringEvaluator.evaluate(pred_missing, eval_spec)
    assert fail is False
    assert details_fail["score"] == 0.0


def test_must_include_with_or_choices():
    eval_spec = {
        "eval_types": ["string_match"],
        "reference_answers": {
            "must_include": ["$249.99 |OR| 249.99", "Canon"]
        },
    }
    ok, _ = WebArenaStringEvaluator.evaluate("Canon printer costs $249.99 on sale.", eval_spec)
    assert ok is True

    ok2, _ = WebArenaStringEvaluator.evaluate("Canon printer is 249.99 dollars.", eval_spec)
    assert ok2 is True

    fail, _ = WebArenaStringEvaluator.evaluate("HP printer is 199.99 dollars.", eval_spec)
    assert fail is False


def test_fuzzy_match_na():
    eval_spec = {
        "eval_types": ["string_match"],
        "reference_answers": {"fuzzy_match": "N/A"},
    }
    ok1, _ = WebArenaStringEvaluator.evaluate("N/A", eval_spec)
    assert ok1 is True

    ok2, _ = WebArenaStringEvaluator.evaluate("There are no reviews found.", eval_spec)
    assert ok2 is True

    fail, _ = WebArenaStringEvaluator.evaluate("The price is $50.", eval_spec)
    assert fail is False


def test_url_match():
    eval_spec = {
        "eval_types": ["url_match"],
        "reference_answers": None,
        "reference_url": "__GITLAB__/dashboard/todos",
    }
    ok, _ = WebArenaStringEvaluator.evaluate("Navigating to http://127.0.0.1:8040/dashboard/todos", eval_spec)
    assert ok is True

    fail, _ = WebArenaStringEvaluator.evaluate("Navigating to http://127.0.0.1:8040/issues", eval_spec)
    assert fail is False


def test_program_html_evaluator():
    eval_spec = {
        "eval_types": ["program_html"],
        "reference_answers": None,
        "reference_url": "",
        "program_html": [
            {
                "url": "__REDDIT__/user/MarvelsGrantMan136",
                "locator": "document.querySelector(\".user-bio__biography\").outerText",
                "required_contents": {
                    "exact_match": "I am a robot"
                }
            }
        ]
    }
    ok, _ = WebArenaStringEvaluator.evaluate("I am a robot", eval_spec)
    assert ok is True

    fail, _ = WebArenaStringEvaluator.evaluate("I am a human", eval_spec)
    assert fail is False

