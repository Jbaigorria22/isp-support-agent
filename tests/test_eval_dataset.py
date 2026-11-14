"""The evaluation dataset must stay valid and in sync with the agent's intents.

These checks cost nothing: they never call the model.
"""

from typing import get_args

from evals.intent_dataset import CASES, by_intent
from fiberlab.agent.brain import Intent

VALID_INTENTS = set(get_args(Intent))


def test_every_case_has_the_required_fields():
    for case in CASES:
        assert case["id"] and case["message"] and case["expected"]


def test_expected_intents_match_the_ones_the_agent_supports():
    """Catches drift: a new intent in the agent, or a typo in the dataset."""
    used = set(by_intent())
    assert used <= VALID_INTENTS, f"unknown intents in the dataset: {used - VALID_INTENTS}"
    assert VALID_INTENTS <= used, f"intents with no test case: {VALID_INTENTS - used}"


def test_ids_are_unique():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))


def test_dataset_is_big_and_balanced_enough():
    assert len(CASES) >= 30
    for intent, count in by_intent().items():
        assert count >= 4, f"{intent} only has {count} cases"


def test_it_includes_hard_cases():
    """A dataset of easy cases proves nothing."""
    hard = [c for c in CASES if "DISCUTIBLE" in c.get("note", "") or "ENGAÑOSO" in c.get("note", "")]
    assert len(hard) >= 5
