"""
main.py — Eklavya AI Content Pipeline (Part 2)
Governed, Auditable, Schema-Validated

Extends Part 1 with:
  - Strict Pydantic schemas (GeneratedContent now includes teacher_notes)
  - Reviewer scores content 1–5 across 4 dimensions (pass: correctness>=4 AND avg>=3.5)
  - RefinerAgent (max 2 attempts, each logged)
  - TaggerAgent (runs only on approved content)
  - RunArtifact — full audit trail saved to SQLite
  - GET /history endpoint
  - POST /generate returns full RunArtifact
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from openai import OpenAI
from pydantic import ValidationError
from datetime import datetime, timezone
import json, os, re, time
from typing import Optional
from dotenv import load_dotenv

from schemas import (
    ContentRequest, GeneratedContent, ReviewResult, ReviewScores,
    FieldFeedback, TagResult, AttemptLog, FinalResult, RunArtifact,
    RunTimestamps, HistoryResponse,
)
from database import init_db, get_db, save_artifact, get_history

load_dotenv()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Eklavya AI Content Pipeline — Part 2",
    description=(
        "Governed, auditable pipeline: Generator → Reviewer → Refiner (max 2×) → Tagger. "
        "Every run produces a full RunArtifact saved to SQLite."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()
    print("[Eklavya] DB initialised.")


# ── LLM client (Groq) ───────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = OpenAI(
    api_key    = GROQ_API_KEY,
    base_url   = "https://api.groq.com/openai/v1",
)
MODEL = "llama-3.1-8b-instant"

INTER_CALL_DELAY = 3   # seconds between agent calls — be kind to free tier


# ── Shared helpers (unchanged from Part 1) ────────────────────────────────────
def extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON robustly."""
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        clean = m.group()
    return json.loads(clean)


def call_llm(system: str, user: str) -> str:
    """Call Grok with basic error handling."""
    try:
        resp = client.chat.completions.create(
            model    = MODEL,
            messages = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature = 0.7,
        )
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "rate" in err.lower():
            raise HTTPException(status_code=429, detail=f"LLM rate limit: {err}")
        if "401" in err or "auth" in err.lower():
            raise HTTPException(status_code=401, detail="Invalid GROQ_API_KEY.")
        raise HTTPException(status_code=500, detail=f"LLM error: {err}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 1 — GeneratorAgent  (UPGRADED from Part 1)
#
# Changes from Part 1:
#   - Output now includes explanation.grade and teacher_notes
#   - Pydantic ValidationError triggers one automatic retry
#   - correct_index (int) replaces answer (str)
# ══════════════════════════════════════════════════════════════════════════════
class GeneratorAgent:
    """
    Generates grade-appropriate educational content.

    Input:  grade (int), topic (str), feedback (optional list of FieldFeedback)
    Output: GeneratedContent (strictly validated by Pydantic)
    """

    SYSTEM = (
        "You are an expert educator. "
        "Always respond with ONLY valid JSON — no markdown, no extra text."
    )

    def _build_prompt(self, grade: int, topic: str, feedback=None) -> str:
        fb_block = ""
        if feedback:
            issues = "\n".join(f'  - [{f.field}] {f.issue}' for f in feedback)
            fb_block = f"\nA previous draft was rejected. Fix these specific issues:\n{issues}\n"

        return f"""Create educational content about "{topic}" for Grade {grade} students.
{fb_block}
Requirements:
- explanation.text: 3–5 sentences, vocabulary for Grade {grade}
- explanation.grade: must be {grade}
- mcqs: exactly 3 questions, each with 4 options, correct_index is 0-based (0=A,1=B,2=C,3=D)
- teacher_notes.learning_objective: one clear sentence
- teacher_notes.common_misconceptions: 2–3 items

Respond ONLY with this exact JSON structure:
{{
  "explanation": {{
    "text": "...",
    "grade": {grade}
  }},
  "mcqs": [
    {{
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_index": 1
    }}
  ],
  "teacher_notes": {{
    "learning_objective": "...",
    "common_misconceptions": ["...", "..."]
  }}
}}"""

    def run(self, grade: int, topic: str, feedback=None) -> GeneratedContent:
        """
        Generates content. On Pydantic ValidationError → retries once.
        On second failure → raises HTTPException (graceful failure).
        """
        for attempt in range(2):   # max 1 retry on schema validation failure
            try:
                raw  = call_llm(self.SYSTEM, self._build_prompt(grade, topic, feedback))
                data = extract_json(raw)
                return GeneratedContent(**data)   # strict Pydantic validation
            except ValidationError as e:
                if attempt == 0:
                    print(f"[Generator] Schema validation failed, retrying… ({e})")
                    time.sleep(INTER_CALL_DELAY)
                    continue
                raise HTTPException(
                    status_code=422,
                    detail=f"Generator produced invalid schema after 2 attempts: {e}"
                )
            except HTTPException:
                raise
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                if attempt == 0:
                    print(f"[Generator] JSON parse failed, retrying… ({e})")
                    time.sleep(INTER_CALL_DELAY)
                    continue
                raise HTTPException(status_code=500, detail=f"Generator: invalid JSON — {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 2 — ReviewerAgent  (UPGRADED from Part 1)
#
# Changes from Part 1:
#   - Returns numeric scores (1–5) across 4 dimensions
#   - Pass threshold computed in Python: correctness >= 4 AND avg >= 3.5
#   - Feedback references specific fields (e.g. "explanation.text")
# ══════════════════════════════════════════════════════════════════════════════
class ReviewerAgent:
    """
    Evaluates generated content quantitatively.

    Pass threshold (documented):
      correctness >= 4  AND  average(all 4 scores) >= 3.5

    Input:  GeneratedContent + grade
    Output: ReviewResult with scores, passed bool, field-level feedback
    """

    # Pass thresholds — change here and README stays in sync
    MIN_CORRECTNESS = 4
    MIN_AVERAGE     = 3.5

    SYSTEM = (
        "You are a strict educational content reviewer. "
        "Always respond with ONLY valid JSON — no markdown, no extra text."
    )

    def run(self, content: GeneratedContent, grade: int) -> ReviewResult:
        prompt = f"""Evaluate this educational content for Grade {grade} students.

Score each dimension 1–5 (5 = excellent):
  age_appropriateness: Is the vocabulary and complexity right for Grade {grade}?
  correctness:         Are all facts and MCQ answers accurate?
  clarity:             Are explanations and questions clearly written?
  coverage:            Does the content adequately cover the topic?

Also provide field-level feedback for any issues found.
Use field paths like: "explanation.text", "mcqs[0].question", "teacher_notes.learning_objective"

Content to review:
{content.model_dump_json(indent=2)}

Respond ONLY with this exact JSON:
{{
  "scores": {{
    "age_appropriateness": 4,
    "correctness": 5,
    "clarity": 4,
    "coverage": 3
  }},
  "feedback": [
    {{"field": "explanation.text", "issue": "describe the issue here"}}
  ]
}}

Note: feedback array can be empty [] if content is excellent."""

        try:
            raw    = call_llm(self.SYSTEM, prompt)
            data   = extract_json(raw)
            scores = ReviewScores(**data["scores"])

            # Pass/fail computed in Python — not delegated to the LLM
            passed = scores.passes   # correctness >= 4 AND average >= 3.5

            feedback = [FieldFeedback(**f) for f in data.get("feedback", [])]

            return ReviewResult(scores=scores, passed=passed, feedback=feedback)

        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            raise HTTPException(status_code=500, detail=f"Reviewer: invalid response — {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 3 — RefinerAgent  (NEW — extracted from inline Part 1 logic)
#
# Part 1 had inline: generator.run(..., feedback=review.feedback)
# Part 2 makes this a proper agent class with bounded retries + logging.
# ══════════════════════════════════════════════════════════════════════════════
class RefinerAgent:
    """
    Improves content using field-level reviewer feedback.

    Rules:
      - Maximum 2 refinement attempts total across the pipeline run
      - Each attempt is logged in the RunArtifact
      - If content still fails after 2 attempts → final status = "rejected"

    Input:  grade, topic, feedback (List[FieldFeedback])
    Output: GeneratedContent (same schema as GeneratorAgent)
    """

    def __init__(self, generator: GeneratorAgent, reviewer: ReviewerAgent):
        self.generator = generator
        self.reviewer  = reviewer

    def run(self, grade: int, topic: str, feedback: list, attempt_num: int) -> tuple:
        """
        Run one refinement attempt.

        Returns:
            (GeneratedContent, ReviewResult) for the new attempt.
        """
        print(f"[Refiner] Attempt {attempt_num} — addressing {len(feedback)} feedback items")
        time.sleep(INTER_CALL_DELAY)
        refined = self.generator.run(grade, topic, feedback=feedback)
        time.sleep(INTER_CALL_DELAY)
        review  = self.reviewer.run(refined, grade)
        return refined, review


# ══════════════════════════════════════════════════════════════════════════════
# Agent 4 — TaggerAgent  (NEW)
#
# Only runs on approved content. Classifies by subject, Bloom's level, difficulty.
# ══════════════════════════════════════════════════════════════════════════════
class TaggerAgent:
    """
    Classifies approved content with educational metadata.

    Only called when final status = "approved".
    Input:  GeneratedContent + grade
    Output: TagResult
    """

    SYSTEM = (
        "You are an educational content classifier. "
        "Always respond with ONLY valid JSON — no markdown, no extra text."
    )

    def run(self, content: GeneratedContent, grade: int) -> TagResult:
        prompt = f"""Classify this educational content.

Content:
{content.model_dump_json(indent=2)}

Respond ONLY with this exact JSON:
{{
  "subject": "Mathematics",
  "topic": "Fractions",
  "grade": {grade},
  "difficulty": "Medium",
  "content_type": ["Explanation", "Quiz"],
  "blooms_level": "Understanding"
}}

Rules:
- difficulty: "Easy" | "Medium" | "Hard"
- content_type: array, pick from ["Explanation", "Quiz", "Activity", "Discussion"]
- blooms_level: one of "Remembering" | "Understanding" | "Applying" | "Analysing" | "Evaluating" | "Creating"
"""
        try:
            raw  = call_llm(self.SYSTEM, prompt)
            data = extract_json(raw)
            return TagResult(**data)
        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            raise HTTPException(status_code=500, detail=f"Tagger: invalid response — {e}")


# ── Instantiate agents ────────────────────────────────────────────────────────
generator = GeneratorAgent()
reviewer  = ReviewerAgent()
refiner   = RefinerAgent(generator, reviewer)
tagger    = TaggerAgent()

MAX_REFINEMENTS = 2   # spec: max 2 refinement attempts


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator — deterministic pipeline loop
#
# Flow:
#   1. Generate
#   2. Review
#   3. If failed AND attempts < MAX_REFINEMENTS → Refine → go to 2
#   4. If failed AND attempts == MAX_REFINEMENTS → status = "rejected"
#   5. If passed → Tag → status = "approved"
#   6. Save RunArtifact to DB
#   7. Return RunArtifact
# ══════════════════════════════════════════════════════════════════════════════
def run_orchestrator(req: ContentRequest, db: Session) -> RunArtifact:
    started_at = datetime.now(timezone.utc)
    attempts   = []

    print(f"[Orchestrator] Starting run — grade={req.grade}, topic={req.topic}")

    # ── Attempt 1: initial generate + review ─────────────────────────────────
    print(f"[Orchestrator] Attempt 1: Generate")
    draft  = generator.run(req.grade, req.topic)
    time.sleep(INTER_CALL_DELAY)

    print(f"[Orchestrator] Attempt 1: Review")
    review = reviewer.run(draft, req.grade)

    attempts.append(AttemptLog(
        attempt = 1,
        draft   = draft,
        review  = review,
        passed  = review.passed,
    ))
    print(f"[Orchestrator] Attempt 1: passed={review.passed}, scores={review.scores.model_dump()}")

    # ── Refinement loop (max MAX_REFINEMENTS total attempts) ─────────────────
    attempt_num = 1
    while not review.passed and attempt_num < MAX_REFINEMENTS + 1:
        attempt_num += 1
        print(f"[Orchestrator] Refinement attempt {attempt_num}")

        draft, review = refiner.run(
            grade       = req.grade,
            topic       = req.topic,
            feedback    = review.feedback,
            attempt_num = attempt_num,
        )

        attempts.append(AttemptLog(
            attempt = attempt_num,
            draft   = draft,
            review  = review,
            passed  = review.passed,
        ))
        print(f"[Orchestrator] Attempt {attempt_num}: passed={review.passed}")

    # ── Final decision ────────────────────────────────────────────────────────
    if review.passed:
        print(f"[Orchestrator] Approved — running Tagger")
        time.sleep(INTER_CALL_DELAY)
        tags   = tagger.run(draft, req.grade)
        final  = FinalResult(status="approved", content=draft, tags=tags)
    else:
        print(f"[Orchestrator] Rejected after {len(attempts)} attempts")
        final  = FinalResult(status="rejected", content=None, tags=None)

    finished_at = datetime.now(timezone.utc)

    artifact = RunArtifact(
        user_id    = req.user_id or "anonymous",
        input      = req,
        attempts   = attempts,
        final      = final,
        timestamps = RunTimestamps(started_at=started_at, finished_at=finished_at),
    )

    # ── Persist to DB ─────────────────────────────────────────────────────────
    save_artifact(
        db           = db,
        artifact_json= artifact.model_dump_json(),
        run_id       = artifact.run_id,
        user_id      = artifact.user_id,
        grade        = req.grade,
        topic        = req.topic,
        final_status = final.status,
    )
    print(f"[Orchestrator] Saved run_id={artifact.run_id}, status={final.status}")

    return artifact


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/generate",
    response_model=RunArtifact,
    summary="Run the full governed pipeline",
    description=(
        "Runs Generator → Reviewer → Refiner (max 2×) → Tagger. "
        "Returns a complete RunArtifact with full audit trail. "
        "Every run is persisted to SQLite."
    ),
)
def generate(req: ContentRequest, db: Session = Depends(get_db)):
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY not set. Add it to backend/.env — get a free key at https://console.groq.com"
        )
    return run_orchestrator(req, db)


@app.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get past pipeline runs",
    description="Returns stored RunArtifacts, newest first. Filter by user_id.",
)
def history(
    user_id: Optional[str] = Query(default=None, description="Filter by user ID"),
    db: Session = Depends(get_db),
):
    records   = get_history(db, user_id=user_id)
    artifacts = [RunArtifact.model_validate_json(r.artifact_json) for r in records]
    return HistoryResponse(total=len(artifacts), artifacts=artifacts)


@app.get("/health", summary="Health check")
def health():
    return {
        "status"  : "ok",
        "version" : "2.0.0",
        "model"   : MODEL,
        "api_key_set": bool(GROQ_API_KEY),
        "max_refinements": MAX_REFINEMENTS,
        "pass_thresholds": {
            "correctness_min": ReviewerAgent.MIN_CORRECTNESS,
            "average_min"    : ReviewerAgent.MIN_AVERAGE,
        },
    }