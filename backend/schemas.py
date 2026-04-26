"""
schemas.py — All Pydantic models for the Eklavya Part 2 pipeline.

Every agent input/output is typed here. The RunArtifact is the
"flight recorder" — it captures the full lifecycle of one pipeline run.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime
import uuid


# ══════════════════════════════════════════════════════════════════════════════
# Generator Agent — Input / Output
# ══════════════════════════════════════════════════════════════════════════════

class ContentRequest(BaseModel):
    """Input to the full pipeline."""
    grade: int = Field(..., ge=1, le=12, description="School grade (1–12)")
    topic: str = Field(..., min_length=2, description="Topic to generate content for")
    user_id: Optional[str] = Field(default="anonymous", description="User identifier for history tracking")


class ExplanationBlock(BaseModel):
    """Structured explanation with grade tag."""
    text: str = Field(..., min_length=10)
    grade: int = Field(..., ge=1, le=12)


class MCQ(BaseModel):
    """Multiple choice question with zero-based correct index."""
    question: str = Field(..., min_length=5)
    options: List[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3, description="Zero-based index of correct option (0=A, 1=B, 2=C, 3=D)")


class TeacherNotes(BaseModel):
    """Metadata for teachers — not shown to students."""
    learning_objective: str
    common_misconceptions: List[str] = Field(..., min_length=1)


class GeneratedContent(BaseModel):
    """
    Full output of the GeneratorAgent.
    Schema is strictly validated — any missing field causes a retry.
    """
    explanation: ExplanationBlock
    mcqs: List[MCQ] = Field(..., min_length=3, max_length=3)
    teacher_notes: TeacherNotes


# ══════════════════════════════════════════════════════════════════════════════
# Reviewer Agent — Output
# ══════════════════════════════════════════════════════════════════════════════

class ReviewScores(BaseModel):
    """
    Quantitative scores (1–5) across four dimensions.

    Pass thresholds (documented):
      - correctness      >= 4  (non-negotiable — wrong facts cannot pass)
      - average of all 4 >= 3.5
    """
    age_appropriateness: int = Field(..., ge=1, le=5)
    correctness:         int = Field(..., ge=1, le=5)
    clarity:             int = Field(..., ge=1, le=5)
    coverage:            int = Field(..., ge=1, le=5)

    @property
    def average(self) -> float:
        return (self.age_appropriateness + self.correctness + self.clarity + self.coverage) / 4

    @property
    def passes(self) -> bool:
        """True only if correctness >= 4 AND average >= 3.5."""
        return self.correctness >= 4 and self.average >= 3.5


class FieldFeedback(BaseModel):
    """
    Field-level feedback so the Refiner knows exactly what to fix.
    e.g. { "field": "explanation.text", "issue": "Too complex for Grade 4" }
    """
    field: str   # e.g. "explanation.text", "mcqs[1].question", "teacher_notes.learning_objective"
    issue: str


class ReviewResult(BaseModel):
    """Full output of the ReviewerAgent."""
    scores:   ReviewScores
    passed:   bool
    feedback: List[FieldFeedback]


# ══════════════════════════════════════════════════════════════════════════════
# Tagger Agent — Output (only runs on approved content)
# ══════════════════════════════════════════════════════════════════════════════

class TagResult(BaseModel):
    """Classification metadata added to approved content only."""
    subject:      str
    topic:        str
    grade:        int
    difficulty:   Literal["Easy", "Medium", "Hard"]
    content_type: List[str]   # e.g. ["Explanation", "Quiz"]
    blooms_level: Literal[
        "Remembering", "Understanding", "Applying",
        "Analysing", "Evaluating", "Creating"
    ]


# ══════════════════════════════════════════════════════════════════════════════
# RunArtifact — The Audit Trail
# ══════════════════════════════════════════════════════════════════════════════

class AttemptLog(BaseModel):
    """
    Records one full attempt: generate → review → (optional refine).
    Every attempt is stored even if it failed.
    """
    attempt:  int
    draft:    GeneratedContent
    review:   ReviewResult
    passed:   bool


class FinalResult(BaseModel):
    """The final outcome after all attempts are exhausted."""
    status:  Literal["approved", "rejected"]
    content: Optional[GeneratedContent] = None   # None if rejected
    tags:    Optional[TagResult]         = None   # None if rejected


class RunTimestamps(BaseModel):
    started_at:  datetime
    finished_at: Optional[datetime] = None


class RunArtifact(BaseModel):
    """
    The complete audit trail for one pipeline execution.
    Stored in DB and returned by POST /generate.
    """
    run_id:     str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id:    str = "anonymous"
    input:      ContentRequest
    attempts:   List[AttemptLog] = []
    final:      Optional[FinalResult] = None
    timestamps: RunTimestamps


# ══════════════════════════════════════════════════════════════════════════════
# API response wrappers
# ══════════════════════════════════════════════════════════════════════════════

class HistoryResponse(BaseModel):
    """Response for GET /history."""
    total:     int
    artifacts: List[RunArtifact]