# Eklavya — AI Content Pipeline 

Eklavya is an agent-based educational content generation and review pipeline. It utilizes extremely fast LLM inference via **Groq** to autonomously generate, review, and optionally refine educational materials (explanations and multiple-choice questions) tailored for specific school grades.

## Architecture & Agent Flow

The application follows a strictly defined agentic workflow:

1. **Generator Agent (Agent 1):** Takes a grade and a topic as input and generates grade-appropriate educational content (an explanation and exactly 3 MCQs).
2. **Reviewer Agent (Agent 2):** Evaluates the generator's drafted content based on three strict criteria:
   - Age-appropriateness
   - Conceptual correctness
   - Clarity
3. **Refinement:** If the Reviewer finds issues (status: `fail`), the feedback is sent back to the Generator Agent for a single pass of refinement to fix the identified problems.

## Tech Stack

* **Backend:** Python, FastAPI, Pydantic, OpenAI API Client (configured for Groq)
* **Frontend:** Python, Streamlit
* **AI Provider:** Groq API (`llama-3.1-8b-instant`)

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- A free **Groq** API Key (get one from [console.groq.com](https://console.groq.com))

### 2. Configure Environment Variables
Inside the `backend` folder, create a file named `.env` and add your Groq API key:
```env
# backend/.env
GROQ_API_KEY="gsk_your_api_key_here"
```

### 3. Install Dependencies
You need to install dependencies for both the backend and frontend.

**Backend Dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

**Frontend Dependencies:**
```bash
cd frontend
pip install -r requirements.txt
```

---

## Running the Application

To run the application locally, you need to start both the backend server and the frontend UI at the same time.

### 1. Start the FastAPI Backend
Open a terminal, navigate to the `backend` directory, and run Uvicorn:
```bash
cd backend
uvicorn main:app --reload
```
*(The backend runs on http://localhost:8000)*

### 2. Start the Streamlit Frontend
Open a **new, separate** terminal, navigate to the `frontend` directory, and run Streamlit:
```bash
cd frontend
streamlit run app.py
```
*(The frontend runs on http://localhost:8501)*

---

## Features
- **Visual Pipeline:** A clean UI flow diagram so users exactly understand the multi-agent pipeline.
- **Raw JSON Inspection:** A toggle allowing reviewers/graders to see the raw structured JSON output produced by each LLM agent directly in the UI.
- **Robust Error Handling:** Frontend gracefully catches rate limits, quota issues, and malformed JSON errors from the AI providers without crashing.
