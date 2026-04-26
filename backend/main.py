

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from openai import OpenAI
from pydantic import ValidationError
from datetime import datetime, timezone
from typing import Optional
import json, os, re, time, logging
from dotenv import load_dotenv

from schemas import (
    ContentRequest, GeneratedContent, ReviewResult, ReviewScores,
    FieldFeedback, TagResult, AttemptLog, FinalResult, RunArtifact,
    RunTimestamps, HistoryResponse,
)
from database import init_db, get_db, save_artifact, get_history

load_dotenv()


logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt= "%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("eklavya")

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
    logger.info("DB initialised.")



GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = OpenAI(
    api_key  = GROQ_API_KEY,
    base_url = "https://api.groq.com/openai/v1",
)
MODEL = "llama-3.1-8b-instant"  

INTER_CALL_DELAY = 3  


# ── Shared helpers ────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON robustly."""
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        clean = m.group()
    return json.loads(clean)


def call_llm(system: str, user: str) -> str:
   
    try:
        resp = client.chat.completions.create(
            model       = MODEL,
            messages    = [
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
# Agent 1 — GeneratorAgent  

# ══════════════════════════════════════════════════════════════════════════════
class GeneratorAgent:
    """
    Generates grade-appropriate educational content.

    Input:  grade (int), topic (str), feedback (optional List[FieldFeedback])
    Output: GeneratedContent (strictly validated by Pydantic)

    Retry policy: on ValidationError or JSON parse failure → retries once,
    then raises HTTPException 422 (graceful failure, never crashes).
    """

    SYSTEM = (
        "You are an expert educator. "
        "Always respond with ONLY valid JSON — no markdown, no extra text."
    )

    def _build_prompt(self, grade: int, topic: str, feedback=None) -> str:
        fb_block = ""
        if feedback:
            issues   = "\n".join(f'  - [{f.field}] {f.issue}' for f in feedback)
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
        On second failure → raises HTTPException 422 (graceful failure).
        """
        for attempt in range(2):  
            try:
                raw  = call_llm(self.SYSTEM, self._build_prompt(grade, topic, feedback))
                data = extract_json(raw)
                return GeneratedContent(**data)  
            except ValidationError as e:
                if attempt == 0:
                    logger.warning("Generator schema validation failed — retrying. Error: %s", e)
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
                    logger.warning("Generator JSON parse failed — retrying. Error: %s", e)
                    time.sleep(INTER_CALL_DELAY)
                    continue
                raise HTTPException(status_code=500, detail=f"Generator: invalid JSON — {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 2 — ReviewerAgent  


# ══════════════════════════════════════════════════════════════════════════════
class ReviewerAgent:
    """
    Evaluates generated content quantitatively.

    Pass threshold (documented — computed in Python via Pydantic property):
      correctness >= 4  AND  average(all 4 scores) >= 3.5

    Moving pass logic to a Pydantic property makes the gatekeeper role
    auditable and independent of LLM hallucinations.

    Input:  GeneratedContent + grade
    Output: ReviewResult with scores, passed bool, field-level feedback
    """

    # Thresholds defined once here — README documents these same values
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

           
            passed   = scores.passes   
            feedback = [FieldFeedback(**f) for f in data.get("feedback", [])]

            return ReviewResult(scores=scores, passed=passed, feedback=feedback)

        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            raise HTTPException(status_code=500, detail=f"Reviewer: invalid response — {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 3 — RefinerAgent 



# ══════════════════════════════════════════════════════════════════════════════
class RefinerAgent:
    """
    Improves content using field-level reviewer feedback.

    Rules (Bounded Retries):
      - Maximum 2 refinement attempts total across the pipeline run
      - Each attempt is logged in the RunArtifact.attempts[]
      - If content still fails after 2 attempts → orchestrator sets status = "rejected"

    Input:  grade, topic, feedback (List[FieldFeedback]), attempt_num
    Output: (GeneratedContent, ReviewResult) tuple
    """

    def __init__(self, generator: GeneratorAgent, reviewer: ReviewerAgent):
        self.generator = generator
        self.reviewer  = reviewer

    def run(self, grade: int, topic: str, feedback: list, attempt_num: int) -> tuple:
        """Run one refinement pass. Returns (new_draft, new_review)."""
        logger.info("Refiner — attempt %d, addressing %d feedback items", attempt_num, len(feedback))
        time.sleep(INTER_CALL_DELAY)
        refined = self.generator.run(grade, topic, feedback=feedback)
        time.sleep(INTER_CALL_DELAY)
        review  = self.reviewer.run(refined, grade)
        return refined, review


# ══════════════════════════════════════════════════════════════════════════════
# Agent 4 — TaggerAgent  
class TaggerAgent:
    """
    Classifies approved content with educational metadata.

    Only called when final status = "approved".
    Input:  GeneratedContent + grade
    Output: TagResult { subject, topic, grade, difficulty, content_type[], blooms_level }
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
- content_type: array, values from ["Explanation", "Quiz", "Activity", "Discussion"]
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


# ── Instantiate agents (singletons per process) ───────────────────────────────
generator = GeneratorAgent()
reviewer  = ReviewerAgent()
refiner   = RefinerAgent(generator, reviewer)
tagger    = TaggerAgent()

MAX_REFINEMENTS = 2  


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator — deterministic, bounded pipeline loop
#
# Bounded Retries: loop hard-coded to terminate after MAX_REFINEMENTS+1 total
# attempts, fulfilling the "explainable and bounded" requirement.
#
# Audit Trail: every attempt appended to artifact.attempts[], capturing the
# "entire lifecycle from draft to final decision" as required.
#
# Flow:
#   1. Generate initial draft
#   2. Review it
#   3. If failed AND refinements_used < MAX_REFINEMENTS → Refine → back to 2
#   4. If failed AND refinements exhausted → status = "rejected"
#   5. If passed → Tag → status = "approved"
#   6. Save RunArtifact to DB
#   7. Return RunArtifact
# ══════════════════════════════════════════════════════════════════════════════
def run_orchestrator(req: ContentRequest, db: Session) -> RunArtifact:
    started_at = datetime.now(timezone.utc)
    attempts   = []

    logger.info("Pipeline start — grade=%d, topic=%s, user=%s", req.grade, req.topic, req.user_id)

    # ── Attempt 1: initial generate + review ─────────────────────────────────
    logger.info("Attempt 1 — Generator")
    draft  = generator.run(req.grade, req.topic)
    time.sleep(INTER_CALL_DELAY)

    logger.info("Attempt 1 — Reviewer")
    review = reviewer.run(draft, req.grade)

    attempts.append(AttemptLog(
        attempt = 1,
        draft   = draft,
        review  = review,
        passed  = review.passed,
    ))
    logger.info(
        "Attempt 1 result — passed=%s, scores=%s, avg=%.2f",
        review.passed,
        review.scores.model_dump(),
        review.scores.average,
    )

    # ── Refinement loop — hard ceiling at MAX_REFINEMENTS ────────────────────
    attempt_num = 1
    while not review.passed and attempt_num <= MAX_REFINEMENTS:
        attempt_num += 1
        logger.info("Refinement attempt %d / %d", attempt_num, MAX_REFINEMENTS + 1)

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
        logger.info("Attempt %d result — passed=%s, avg=%.2f", attempt_num, review.passed, review.scores.average)

    # ── Final decision ────────────────────────────────────────────────────────
    if review.passed:
        logger.info("Approved — running Tagger")
        time.sleep(INTER_CALL_DELAY)
        tags  = tagger.run(draft, req.grade)
        final = FinalResult(status="approved", content=draft, tags=tags)
    else:
        logger.warning("Rejected — failed after %d attempt(s)", len(attempts))
        final = FinalResult(status="rejected", content=None, tags=None)

    finished_at = datetime.now(timezone.utc)
    elapsed     = (finished_at - started_at).total_seconds()

    artifact = RunArtifact(
        user_id    = req.user_id or "anonymous",
        input      = req,
        attempts   = attempts,
        final      = final,
        timestamps = RunTimestamps(started_at=started_at, finished_at=finished_at),
    )

    # ── Persist to DB (Audit Trail) ───────────────────────────────────────────
    save_artifact(
        db            = db,
        artifact_json = artifact.model_dump_json(),
        run_id        = artifact.run_id,
        user_id       = artifact.user_id,
        grade         = req.grade,
        topic         = req.topic,
        final_status  = final.status,
    )
    logger.info(
        "Saved — run_id=%s, status=%s, attempts=%d, elapsed=%.1fs",
        artifact.run_id, final.status, len(attempts), elapsed,
    )

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
        "status"          : "ok",
        "version"         : "2.0.0",
        "provider"        : "Groq",
        "model"           : MODEL,
        "api_key_set"     : bool(GROQ_API_KEY),
        "max_refinements" : MAX_REFINEMENTS,
        "pass_thresholds" : {
            "correctness_min" : ReviewerAgent.MIN_CORRECTNESS,
            "average_min"     : ReviewerAgent.MIN_AVERAGE,
        },
    }