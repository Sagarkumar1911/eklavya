from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Eklavya AI Content Pipeline",
    description="Agent-based pipeline: Generator Agent → Reviewer Agent → Refinement",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

MODEL = "llama-3.1-8b-instant"  


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


# ── Helper ────────────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON robustly."""
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    json_match = re.search(r"\{.*\}", clean, re.DOTALL)
    if json_match:
        clean = json_match.group()
    return json.loads(clean)


def call_groq(system: str, user: str) -> str:
    """Call Groq via OpenAI-compatible API."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        if "429" in str(e) or "rate" in str(e).lower():
            raise HTTPException(status_code=429, detail="Groq rate limit exceeded.")
        if "401" in str(e) or "auth" in str(e).lower():
            raise HTTPException(status_code=401, detail="Invalid API key.")
        raise HTTPException(status_code=500, detail=f"API error: {e}")


# --- Generator Agent ---
class GeneratorAgent:
    """Generates grade-appropriate educational content (explanation + MCQs)."""

    def run(self, grade: int, topic: str, feedback: Optional[List[str]] = None) -> GeneratedContent:
        """
        Args:
            grade:    Target school grade (1–12).
            topic:    Subject/topic to generate content for.
            feedback: Optional reviewer feedback for refinement pass.
        Returns:
            GeneratedContent with explanation and 3 MCQs.
        """
        feedback_block = ""
        if feedback:
            issues = "\n".join(f"  - {f}" for f in feedback)
            feedback_block = f"\nA previous draft was rejected. Fix these issues:\n{issues}\n"

        system = f"""You are an expert educator creating content for Grade {grade} students.
Always respond with ONLY valid JSON — no markdown, no explanation, no extra text.
{feedback_block}"""

        user = f"""Create educational content about: "{topic}"

Requirements:
- Language and vocabulary must match Grade {grade} level
- Explanation: 3 to 5 clear sentences  
- Include exactly 3 multiple-choice questions
- Each question has 4 options labeled A, B, C, D
- The "answer" field must be just the letter (e.g. "B")
- All concepts must be factually correct

Output format (JSON only):
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
            text = call_groq(system, user)
            data = extract_json(text)
            return GeneratedContent(**data)
        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Generator Agent: invalid JSON — {e}")


# --- Reviewer Agent ---
class ReviewerAgent:
    """Evaluates generated content for age-appropriateness, correctness, and clarity."""

    def run(self, content: GeneratedContent, grade: int) -> ReviewResult:
        """
        Args:
            content: The GeneratedContent produced by GeneratorAgent.
            grade:   Target grade, used to judge age-appropriateness.
        Returns:
            ReviewResult with status "pass" or "fail" and specific feedback.
        """
        system = """You are a strict educational content reviewer.
Always respond with ONLY valid JSON — no markdown, no explanation, no extra text."""

        user = f"""Evaluate this content for Grade {grade} students against three criteria:

1. Age-appropriateness — is vocabulary and complexity right for Grade {grade}?
2. Conceptual correctness — are all facts and MCQ answers accurate?
3. Clarity — are explanations and questions clearly written?

Content to review:
{content.model_dump_json(indent=2)}

Rules:
- If ALL three criteria are met → "status": "pass", feedback = what was done well (3–4 points)
- If ANY criterion fails       → "status": "fail", feedback = specific problems to fix

Output format (JSON only):
{{
  "status": "pass",
  "feedback": ["...", "..."]
}}"""

        try:
            text = call_groq(system, user)
            data = extract_json(text)
            return ReviewResult(**data)
        except HTTPException:
            raise
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Reviewer Agent: invalid JSON — {e}")


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
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY not set. Add it to backend/.env — get a free key at https://console.groq.com"
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
    return {
        "status": "ok",
        "model": MODEL,
        "provider": "Groq",
        "api_key_set": bool(GROQ_API_KEY),
    }
