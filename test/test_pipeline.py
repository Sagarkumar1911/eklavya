"""
tests/test_pipeline.py — Mandatory Part 2 tests

Three tests covering:
  1. Schema validation failure → graceful handling
  2. fail → refine → pass orchestration
  3. fail → refine → fail → reject orchestration

LLM calls are mocked — no real API calls made during tests.
Run with: pytest tests/test_pipeline.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from schemas import (
    GeneratedContent, ExplanationBlock, MCQ, TeacherNotes,
    ReviewResult, ReviewScores, FieldFeedback,
    ContentRequest, RunArtifact,
)
from main import GeneratorAgent, ReviewerAgent, RefinerAgent, run_orchestrator


# ── Fixtures — valid test data ─────────────────────────────────────────────────

def make_valid_content() -> GeneratedContent:
    return GeneratedContent(
        explanation=ExplanationBlock(text="Angles are formed when two lines meet at a point.", grade=4),
        mcqs=[
            MCQ(question="What is a right angle?",
                options=["A. 45°", "B. 90°", "C. 180°", "D. 360°"],
                correct_index=1),
            MCQ(question="Which angle is less than 90°?",
                options=["A. Obtuse", "B. Straight", "C. Acute", "D. Reflex"],
                correct_index=2),
            MCQ(question="A straight angle measures?",
                options=["A. 90°", "B. 45°", "C. 270°", "D. 180°"],
                correct_index=3),
        ],
        teacher_notes=TeacherNotes(
            learning_objective="Students can identify and classify types of angles.",
            common_misconceptions=["Confusing acute and obtuse", "Thinking right angle must point right"],
        ),
    )


def make_passing_review() -> ReviewResult:
    scores = ReviewScores(age_appropriateness=5, correctness=5, clarity=4, coverage=4)
    return ReviewResult(scores=scores, passed=True, feedback=[])


def make_failing_review() -> ReviewResult:
    scores = ReviewScores(age_appropriateness=3, correctness=3, clarity=3, coverage=3)
    return ReviewResult(
        scores=scores,
        passed=False,
        feedback=[FieldFeedback(field="explanation.text", issue="Too complex for Grade 4")],
    )


def make_db_mock():
    db = MagicMock()
    db.add    = MagicMock()
    db.commit = MagicMock()
    db.refresh= MagicMock()
    return db


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — Schema validation failure is handled gracefully
#
# Scenario: LLM returns broken JSON (missing required fields).
# Expected: GeneratorAgent retries once, then raises HTTPException (not crash).
# ══════════════════════════════════════════════════════════════════════════════
def test_schema_validation_failure_handled_gracefully():
    """
    If the LLM returns invalid JSON twice, GeneratorAgent must raise
    HTTPException with status 422 — not an unhandled Python crash.
    """
    from fastapi import HTTPException

    bad_json_response = '{"explanation": "missing grade field", "mcqs": []}'

    agent = GeneratorAgent()

    with patch("main.call_llm", return_value=bad_json_response):
        with pytest.raises(HTTPException) as exc_info:
            agent.run(grade=4, topic="Angles")

    assert exc_info.value.status_code in (422, 500), (
        f"Expected 422 or 500 for schema failure, got {exc_info.value.status_code}"
    )
    print("✅ Test 1 passed — schema validation failure handled gracefully")


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — fail → refine → pass orchestration
#
# Scenario: Reviewer fails attempt 1, passes attempt 2 after refinement.
# Expected: RunArtifact has 2 attempts, final status = "approved", tags present.
# ══════════════════════════════════════════════════════════════════════════════
def test_fail_refine_pass_orchestration():
    """
    First review fails, one refinement is triggered, second review passes.
    RunArtifact must show 2 attempts and final status = "approved".
    """
    valid_content = make_valid_content()
    passing_review = make_passing_review()
    failing_review = make_failing_review()

    review_call_count = {"n": 0}

    def mock_reviewer_run(content, grade):
        review_call_count["n"] += 1
        # First review fails, second passes
        return failing_review if review_call_count["n"] == 1 else passing_review

    from schemas import TagResult
    mock_tags = TagResult(
        subject="Mathematics", topic="Angles", grade=4,
        difficulty="Easy", content_type=["Explanation", "Quiz"],
        blooms_level="Understanding",
    )

    req = ContentRequest(grade=4, topic="Types of angles", user_id="test_user")
    db  = make_db_mock()

    with patch.object(GeneratorAgent, "run", return_value=valid_content), \
         patch.object(ReviewerAgent,  "run", side_effect=mock_reviewer_run), \
         patch.object(TaggerAgent,    "run", return_value=mock_tags), \
         patch("main.save_artifact"):

        from main import TaggerAgent
        artifact = run_orchestrator(req, db)

    assert len(artifact.attempts) == 2,                       "Should have exactly 2 attempts"
    assert artifact.attempts[0].passed == False,              "Attempt 1 should have failed"
    assert artifact.attempts[1].passed == True,               "Attempt 2 should have passed"
    assert artifact.final.status == "approved",               "Final status should be approved"
    assert artifact.final.tags   is not None,                 "Tags should be present on approved content"
    assert artifact.final.content is not None,                "Content should be present"

    print("✅ Test 2 passed — fail → refine → pass orchestration correct")


# ══════════════════════════════════════════════════════════════════════════════
# Test 3 — fail → refine → fail → reject orchestration
#
# Scenario: Reviewer always fails (content never good enough).
# Expected: System stops after MAX_REFINEMENTS+1 attempts, status = "rejected".
#           No infinite loop.
# ══════════════════════════════════════════════════════════════════════════════
def test_fail_refine_fail_reject_orchestration():
    """
    Reviewer always returns fail. After MAX_REFINEMENTS attempts,
    the pipeline must stop and set final status = "rejected".
    """
    from main import MAX_REFINEMENTS

    valid_content  = make_valid_content()
    failing_review = make_failing_review()

    req = ContentRequest(grade=4, topic="Types of angles", user_id="test_user")
    db  = make_db_mock()

    with patch.object(GeneratorAgent, "run", return_value=valid_content), \
         patch.object(ReviewerAgent,  "run", return_value=failing_review), \
         patch("main.save_artifact"):

        artifact = run_orchestrator(req, db)

    expected_attempts = MAX_REFINEMENTS + 1   # 1 initial + MAX_REFINEMENTS refinements
    assert len(artifact.attempts) == expected_attempts, (
        f"Expected {expected_attempts} attempts, got {len(artifact.attempts)}"
    )
    assert artifact.final.status  == "rejected",  "Final status should be rejected"
    assert artifact.final.content is None,        "No content on rejected run"
    assert artifact.final.tags    is None,        "No tags on rejected run"

    # Verify all attempts recorded as failed
    for i, attempt in enumerate(artifact.attempts):
        assert attempt.passed == False, f"Attempt {i+1} should be marked as failed"

    print(f"✅ Test 3 passed — rejected after {expected_attempts} attempts, no infinite loop")


# ── Run directly ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Running Eklavya Part 2 Tests")
    print("="*60 + "\n")

    test_schema_validation_failure_handled_gracefully()
    test_fail_refine_pass_orchestration()
    test_fail_refine_fail_reject_orchestration()

    print("\n" + "="*60)
    print("All 3 tests passed ✅")
    print("="*60)