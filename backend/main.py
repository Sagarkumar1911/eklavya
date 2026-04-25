from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import google.generativeai as genai
import json
import os
import re
import time
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Eklavya AI Content Pipeline",
    description="Agent-based pipeline: Generator Agent → Reviewer Agent → Refinement",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Gemini setup ──────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

# gemini-1.5-flash = 1500 req/day FREE  ✅
# gemini-2.5-flash = 20   req/day FREE  ❌ (too low)
GEMINI_MODEL = "gemini-1.5-flash"


# ── Pydantic Schemas ──────────────────────────────────────────────────────────
class ContentRequest(BaseModel):
    grade: int
    topic: str

class MCQ(BaseModel):
    question: str
    options: List[str]
    answer: str

class GeneratedContent(BaseModel):
    explanation: str
    mcqs: List[MCQ]

class ReviewResult(BaseModel):
    status: str          # "pass" | "fail"
    feedback: List[str]

class PipelineResponse(BaseModel):
    generated: GeneratedContent
    review: ReviewResult
    refined: Optional[GeneratedContent] = None
    refinement_triggered: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON robustly."""
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    json_match = re.search(r"\{.*\}", clean, re.DOTALL)
    if json_match:
        clean = json_match.group()
    return json.loads(clean)


def call_gemini_with_retry(model, prompt: str, retries: int = 3, wait: int = 15) -> str:
    """Call Gemini with automatic retry on 429 rate-limit errors."""
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                if attempt < retries - 1:
                    time.sleep(wait)   # wait then retry
                    continue
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "Gemini free-tier rate limit hit. "
                        "Wait a minute and try again, or get a paid key at https://ai.google.dev."
                    )
                )
            raise HTTPException(status_code=500, detail=f"Gemini API error: {err}")
    raise HTTPException(status_code=500, detail="Gemini API failed after retries.")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 1 — Generator
# Responsibility: Generate draft educational content for a given grade & topic.
# Input:  ContentRequest  { grade, topic }
# Output: GeneratedContent { explanation, mcqs[] }
# ══════════════════════════════════════════════════════════════════════════════
class GeneratorAgent:
    """Generates grade-appropriate educational content (explanation + MCQs)."""

    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def run(self, grade: int, topic: str, feedback: Optional[List[str]] = None) -> GeneratedContent:
        feedback_block = ""
        if feedback:
            issues = "\n".join(f"  - {f}" for f in feedback)
            feedback_block = f"\nA previous draft was rejected. Fix these issues:\n{issues}\n"

        prompt = f"""You are an expert educator writing for Grade {grade} students.
{feedback_block}
Create educational content about: "{topic}"

Requirements:
- Language and vocabulary must match Grade {grade} level
- Explanation: 3 to 5 clear sentences
- Include exactly 3 multiple-choice questions
- Each question has 4 options labeled A, B, C, D
- The "answer" field must be just the letter (e.g. "B")
- All concepts must be factually correct

Respond ONLY with valid JSON — no markdown, no extra text:
{{
  "explanation": "...",
  "mcqs": [
    {{
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "answer": "B"
    }}
  ]
}}"""

        try:
            text = call_gemini_with_retry(self.model, prompt)
            data = extract_json(text)
            return GeneratedContent(**data)
        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Generator Agent Error: invalid JSON from model: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Agent 2 — Reviewer
# Responsibility: Evaluate the Generator's output for quality.
# Input:  GeneratedContent + grade
# Output: ReviewResult { status: "pass"|"fail", feedback: [...] }
# ══════════════════════════════════════════════════════════════════════════════
class ReviewerAgent:
    """Evaluates generated content for age-appropriateness, correctness, and clarity."""

    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def run(self, content: GeneratedContent, grade: int) -> ReviewResult:
        prompt = f"""You are a strict educational content reviewer.
Evaluate this content for Grade {grade} students against three criteria:

1. Age-appropriateness — is vocabulary and complexity right for Grade {grade}?
2. Conceptual correctness — are all facts and MCQ answers accurate?
3. Clarity — are explanations and questions clearly written?

Content:
{content.model_dump_json(indent=2)}

Rules:
- If ALL three criteria are met → "status": "pass",  feedback = what was done well (3–4 points)
- If ANY criterion fails       → "status": "fail",  feedback = specific problems to fix

Respond ONLY with valid JSON — no markdown:
{{
  "status": "pass",
  "feedback": ["...", "..."]
}}"""

        try:
            text = call_gemini_with_retry(self.model, prompt)
            data = extract_json(text)
            return ReviewResult(**data)
        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Reviewer Agent Error: invalid JSON from model: {e}")


# ── Instantiate agents ────────────────────────────────────────────────────────
generator = GeneratorAgent()
reviewer  = ReviewerAgent()


# ── Pipeline Endpoint ─────────────────────────────────────────────────────────
@app.post(
    "/generate",
    response_model=PipelineResponse,
    summary="Run the full agent pipeline",
    description=(
        "Runs Generator → Reviewer → (optional Refinement). "
        "If Reviewer returns 'fail', Generator re-runs once with feedback embedded."
    ),
)
def run_pipeline(req: ContentRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY not set. Add it to backend/.env — get a free key at https://aistudio.google.com/app/apikey"
        )

    # Step 1 — Generator Agent
    generated: GeneratedContent = generator.run(req.grade, req.topic)

    # Step 2 — Reviewer Agent
    review: ReviewResult = reviewer.run(generated, req.grade)

    # Step 3 — Refinement (one pass only, only if review failed)
    refined: Optional[GeneratedContent] = None
    if review.status == "fail":
        refined = generator.run(req.grade, req.topic, feedback=review.feedback)

    return PipelineResponse(
        generated=generated,
        review=review,
        refined=refined,
        refinement_triggered=(review.status == "fail"),
    )


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok", "model": GEMINI_MODEL, "api_key_set": bool(GEMINI_API_KEY)}