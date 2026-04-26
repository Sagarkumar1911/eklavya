# 📚 Eklavya — AI Content Pipeline

> **Making learning accessible** · An AI-powered system that generates, reviews, and refines educational content for any grade and topic.

---

## What is Eklavya?

Eklavya is an AI pipeline built for **Eklavya Education** that automatically creates high-quality educational content — explanations, multiple-choice questions, and teacher notes — tailored to a specific school grade and topic.

The system is designed around a core idea: **AI-generated content should not be published without review**. Every piece of content passes through a multi-agent pipeline where one agent generates, another critiques, and a third refines — before a final tagger classifies the approved content for the content library.

The name is inspired by Eklavya from the Mahabharata — a self-taught student who achieved mastery through dedication, symbolising learning without barriers.

---

## Evolution: Part 1 → Part 2

This repository contains both versions of the pipeline, built iteratively as an AI Developer Assessment.

---

## Part 1 — Basic Agent Pipeline

> *Goal: Prove the multi-agent concept works.*

### What it does

A simple two-agent pipeline that generates educational content and reviews it once. If the review fails, the Generator is re-run with the feedback embedded — one refinement pass.

### Agents

| Agent | Role | Output |
|---|---|---|
| **GeneratorAgent** | Generates explanation + 3 MCQs for a given grade and topic | `{ explanation, mcqs[] }` |
| **ReviewerAgent** | Evaluates for age-appropriateness, correctness, clarity | `{ status: "pass/fail", feedback: [...] }` |

### Pipeline Flow

```
Input (grade + topic)
      ↓
 Generator  →  Reviewer  →  pass? → Final Output
                  ↓
                fail? → Re-run Generator with feedback (1× only)
                              ↓
                         Final Output
```

### Key Characteristics
- ✅ Two agent classes with clear responsibilities
- ✅ Structured JSON input/output (Pydantic)
- ✅ One refinement pass on failure
- ✅ Streamlit UI showing all pipeline steps
- ✅ FastAPI backend with `/generate` endpoint
- ⚠️ Pass/fail was a simple text status — no scoring
- ⚠️ No persistence — results were not stored
- ⚠️ No audit trail — runs could not be replayed or inspected
- ⚠️ No tests

### Tech Stack (Part 1)
- **Backend:** Python · FastAPI
- **Frontend:** Streamlit
- **LLM:** Groq (`llama-3.1-8b-instant`) — free tier
- **Validation:** Pydantic v2

---

## Part 2 — Governed, Auditable Pipeline

> *Goal: Make the pipeline production-worthy — schema-validated, quantitatively scored, bounded, auditable, and testable.*

Part 2 is a **direct extension** of Part 1. No code was thrown away — every agent was upgraded in place and new capabilities were layered on top.

### What changed from Part 1

| Capability | Part 1 | Part 2 |
|---|---|---|
| Generator output schema | `explanation (str)`, `mcqs[]` | + `explanation.grade`, + `teacher_notes` |
| Schema validation | Basic JSON parse | Pydantic strict validation + 1 auto-retry |
| Review output | `status: "pass/fail"`, text feedback | Numeric scores (1–5 × 4 dimensions) + field-level feedback |
| Pass/fail logic | LLM decided | Python `ReviewScores.passes` property — deterministic |
| Refinement | 1 pass, inline | Dedicated `RefinerAgent` class, max 2 passes, each logged |
| Content tagging | ❌ None | `TaggerAgent` — Bloom's level, difficulty, subject |
| Audit trail | ❌ None | Full `RunArtifact` with every attempt, score, and timestamp |
| Persistence | ❌ None | SQLite via SQLAlchemy — every run saved |
| History endpoint | ❌ None | `GET /history?user_id=` |
| Logging | `print()` statements | Python `logging` module — structured, level-aware |
| Tests | ❌ None | 3 pytest tests — all LLM calls mocked |

---

### Agents (Part 2)

#### Agent 1 — GeneratorAgent *(upgraded)*
Produces draft educational content with strict Pydantic schema validation.

| | |
|---|---|
| **Input** | `grade`, `topic`, optional `feedback` (List[FieldFeedback]) |
| **Output** | `GeneratedContent { explanation: {text, grade}, mcqs[3], teacher_notes }` |
| **On schema fail** | Retries once automatically → raises `422` gracefully |
| **Retry policy** | Max 1 automatic retry on `ValidationError` or JSON parse failure |

#### Agent 2 — ReviewerAgent *(upgraded — now a Gatekeeper)*
Quantitatively evaluates content. Pass/fail is computed in Python — never delegated to the LLM.

| | |
|---|---|
| **Input** | `GeneratedContent` + `grade` |
| **Output** | `ReviewResult { scores: {1–5 × 4}, passed: bool, feedback: [FieldFeedback] }` |
| **Pass logic** | `ReviewScores.passes` Pydantic property — `correctness ≥ 4 AND average ≥ 3.5` |
| **Feedback format** | `{ "field": "explanation.text", "issue": "..." }` — field-level, not generic |

#### Agent 3 — RefinerAgent *(new)*
Improves content using the Reviewer's specific field-level feedback. Hard limit of 2 passes.

| | |
|---|---|
| **Input** | `grade`, `topic`, `feedback` (List[FieldFeedback]) |
| **Output** | New `(GeneratedContent, ReviewResult)` pair |
| **Max attempts** | 2 refinement passes. If still failing → `status: "rejected"` |
| **Logging** | Every attempt logged to `RunArtifact.attempts[]` |

#### Agent 4 — TaggerAgent *(new)*
Classifies approved content only. Never runs on rejected content.

| | |
|---|---|
| **Input** | `GeneratedContent` + `grade` |
| **Output** | `TagResult { subject, topic, grade, difficulty, content_type[], blooms_level }` |
| **Bloom's levels** | Remembering · Understanding · Applying · Analysing · Evaluating · Creating |

---

### Pipeline Flow (Part 2)

```
Input (grade + topic)
       │
       ▼
┌─────────────────┐
│ GeneratorAgent  │  explanation + 3 MCQs + teacher_notes
│   (Agent 1)     │  Pydantic-validated — retries once on schema failure
└─────────────────┘
       │
       ▼
┌─────────────────┐
│ ReviewerAgent   │  Scores 1–5 across 4 dimensions
│   (Agent 2)     │  Pass threshold computed in Python (not by LLM)
└─────────────────┘
       │
  passed? ──── YES ─────────────────────────────────────────┐
       │                                                     │
       NO                                                    ▼
       │                                          ┌─────────────────┐
┌─────────────────┐   still failing after 2×      │  TaggerAgent    │
│  RefinerAgent   │ ──────────────────────────►   │   (Agent 4)     │
│   (Agent 3)     │        → REJECTED             │  approved only  │
│   max 2 passes  │                               └─────────────────┘
└─────────────────┘                                          │
                                                             ▼
                                                   ┌─────────────────┐
                                                   │   RunArtifact   │
                                                   │  saved to DB    │
                                                   └─────────────────┘
```

---

### Pass / Fail Criteria

```
PASS requires ALL of:
  correctness score  >= 4    (wrong facts can never pass — non-negotiable)
  average of all 4   >= 3.5  (overall quality floor)

FAIL triggers RefinerAgent (max 2×) → then REJECTED if still failing
```

Scores (1–5) across four dimensions:

| Dimension | What it measures |
|---|---|
| `age_appropriateness` | Vocabulary and complexity for the target grade |
| `correctness` | Factual accuracy of explanation and MCQ answers |
| `clarity` | Readability and structure |
| `coverage` | How well the topic is covered |

**Why pass logic is in Python and not in the LLM:**
`ReviewScores.passes` is a Pydantic property — it always produces the same result for the same scores. The LLM only provides raw numbers. This makes the gatekeeper role deterministic, auditable, and independent of LLM hallucinations.

---

### Orchestration Decisions

| Decision | Rationale |
|---|---|
| Pass threshold in `ReviewScores.passes` property | Deterministic, auditable — LLM cannot hallucinate a pass |
| Hard ceiling `MAX_REFINEMENTS = 2` | Bounded cost, loop always terminates |
| RunArtifact stored as JSON blob | Full audit trail in one DB read — no joins needed |
| `logging` module instead of `print()` | Structured, level-aware, production-ready |
| SQLite default, PostgreSQL via env var | Zero setup for assessment; one env var change for production |
| TaggerAgent only on approved content | Tagging rejected content wastes tokens and pollutes the index |
| `INTER_CALL_DELAY = 3s` between calls | Stays within Groq free-tier rate limits (30 RPM) |

---

### Trade-offs

| Choice | Gained | Gave up |
|---|---|---|
| JSON blob in DB | Simple schema, full artifact in one read | Can't SQL-filter on scores without parsing |
| Groq `llama-3.1-8b-instant` | 14,400 req/day free, no strict RPM wall | Slightly less capable than GPT-4 class |
| Pydantic strict validation | Auto-validation, clear errors, testable | More verbose schema definitions |
| SQLite default | Zero setup, portable | Not suitable for multi-process production |
| Single `call_llm()` for all agents | DRY, one place for auth/retry | Less per-agent flexibility |

---

## Project Structure

```
eklavya/
├── backend/
│   ├── main.py                # FastAPI — all 4 agents + orchestrator + endpoints
│   ├── schemas.py             # All Pydantic models (GeneratedContent, RunArtifact, etc.)
│   ├── database.py            # SQLAlchemy + SQLite persistence
│   ├── requirements.txt
│   ├── .env.example           # Environment variable template
│   └── tests/
│       └── test_pipeline.py   # 3 tests — all LLM calls mocked with @patch
└── frontend/
    ├── app.py                 # Streamlit UI — Generate tab + History tab
    └── requirements.txt
```

---

## Setup

### 1. Get a free Groq API key
Go to **https://console.groq.com** → API Keys → Create API key.

> ✅ Groq free tier: **14,400 req/day**, **30 req/min** on `llama-3.1-8b-instant` — no credit card needed.

### 2. Configure environment
```bash
cd backend
cp .env.example .env
# Paste your GROQ_API_KEY into .env
```

### 3. Install dependencies
```bash
# Backend
cd backend && pip install -r requirements.txt

# Frontend
cd frontend && pip install -r requirements.txt
```

### 4. Run
```bash
# Terminal 1 — Backend
cd backend
uvicorn main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs

# Terminal 2 — Frontend
cd frontend
streamlit run app.py
# → http://localhost:8501
```

### 5. Run tests
```bash
cd backend
pytest tests/test_pipeline.py -v
```
> All LLM calls are mocked — runs offline instantly, no API key needed.

---

## API Reference

### `POST /generate`
Run the full pipeline. Returns a complete `RunArtifact`.

```json
// Request
{ "grade": 4, "topic": "Types of angles", "user_id": "alice" }

// Response
{
  "run_id": "94dff45c-...",
  "user_id": "alice",
  "input": { "grade": 4, "topic": "Types of angles" },
  "attempts": [
    {
      "attempt": 1,
      "draft": { "explanation": {...}, "mcqs": [...], "teacher_notes": {...} },
      "review": { "scores": {...}, "passed": false, "feedback": [...] },
      "passed": false
    },
    {
      "attempt": 2,
      "draft": { ... },
      "review": { "scores": {...}, "passed": true, "feedback": [] },
      "passed": true
    }
  ],
  "final": {
    "status": "approved",
    "content": { ... },
    "tags": { "subject": "Mathematics", "blooms_level": "Understanding", "difficulty": "Medium" }
  },
  "timestamps": { "started_at": "2026-04-26T15:09:07Z", "finished_at": "2026-04-26T15:09:16Z" }
}
```

### `GET /history?user_id=alice`
Returns all stored `RunArtifact` records, newest first.

### `GET /health`
```json
{
  "status": "ok",
  "version": "2.0.0",
  "provider": "Groq",
  "model": "llama3-8b-8192",
  "max_refinements": 2,
  "pass_thresholds": { "correctness_min": 4, "average_min": 3.5 }
}
```

---

## Tests

| Test | Scenario | Verifies |
|---|---|---|
| `test_schema_validation_failure_handled_gracefully` | LLM returns invalid JSON twice | Raises `HTTPException` — does not crash |
| `test_fail_refine_pass_orchestration` | Fails attempt 1, passes attempt 2 | 2 attempts logged, `status=approved`, tags present |
| `test_fail_refine_fail_reject_orchestration` | Always fails | Stops at `MAX_REFINEMENTS+1`, `status=rejected`, Tagger never called |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+ · FastAPI · Uvicorn |
| Frontend | Streamlit |
| LLM | Groq (`llama3-8b-8192`) — free tier |
| Validation | Pydantic v2 |
| Persistence | SQLAlchemy + SQLite |
| Testing | pytest + unittest.mock |
| Config | python-dotenv |