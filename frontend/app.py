import streamlit as st
import requests

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Eklavya — AI Content Pipeline",
    page_icon="📚",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,600;1,400&family=DM+Sans:wght@400;500&display=swap');
html, body, [data-testid="stAppViewContainer"], .stApp {
    font-family: 'DM Sans', sans-serif;
    background-color: #ffffff !important;
    color: #1a1814 !important;
}

.logo { font-family:'Fraunces',serif; font-size:3.5rem; color:#2d6a4f; margin-bottom: 0px; line-height: 1.2; }
.tag  { color:#6b6560; font-size:1.15rem; margin-top:0px; margin-bottom:1.5rem; }

/* Fix toggle visibility against forced white background */
div[data-testid="stToggle"] p, div[data-testid="stNumberInput"] p, div[data-testid="stTextInput"] p {
    color: #1a1814 !important;
    font-weight: 600 !important;
}
/* Fix toggle visibility against forced white background */
div[data-baseweb="checkbox"] > div:first-child {
    background-color: #3b82f6 !important; /* visible blue when off */
}
div[data-baseweb="checkbox"] div[data-checked="true"] {
    background-color: #1d4ed8 !important; /* darker blue when on */
}

/* Pipeline flow diagram */
.pipeline-flow {
    display:flex; align-items:center; justify-content:center;
    gap:0; background:#f7f5f0; border:1px solid #e4e0d8;
    border-radius:12px; padding:16px 20px; margin-bottom:1.5rem;
}
.pf-node {
    display:flex; flex-direction:column; align-items:center;
    background:#fff; border:1px solid #e4e0d8; border-radius:10px;
    padding:10px 18px; min-width:110px; text-align:center;
}
.pf-node .icon { font-size:1.4rem; margin-bottom:4px; }
.pf-node .lbl  { font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:#2d6a4f; }
.pf-node .sub  { font-size:0.65rem; color:#6b6560; margin-top:2px; }
.pf-arrow      { font-size:1.2rem; color:#b0a99f; padding:0 6px; }
.pf-node.active-node { border-color:#2d6a4f; background:#e8f5ee; }

/* Step headers */
.step-box {
    padding:12px 18px; border-radius:10px; margin:6px 0 4px 0;
    font-weight:600; font-size:0.82rem; text-transform:uppercase; letter-spacing:0.07em;
}
.s-green { background:#e8f5ee; color:#2d6a4f; border-left:4px solid #2d6a4f; }
.s-blue  { background:#dbeafe; color:#1e40af; border-left:4px solid #1e40af; }
.s-amber { background:#fef3c7; color:#b45309; border-left:4px solid #d97706; }
.s-done  { background:#e8f5ee; color:#2d6a4f; border-left:4px solid #2d6a4f; }

/* Content blocks */
.expl { font-size:0.95rem; line-height:1.75; color:#1a1814; background:#f7f5f0; padding:14px 18px; border-radius:10px; border:1px solid #e4e0d8; }
.mcq  { border:1px solid #e4e0d8; border-radius:10px; padding:14px 16px; margin-bottom:10px; background:#fafaf8; }
.mcq-q { font-weight:600; font-size:0.9rem; margin-bottom:10px; color:#1a1814; }
.opt         { display:inline-block; padding:4px 13px; border-radius:99px; font-size:0.82rem; margin:3px; border:1px solid #e4e0d8; background:#fff; color:#1a1814; }
.opt-correct { display:inline-block; padding:4px 13px; border-radius:99px; font-size:0.82rem; margin:3px; background:#e8f5ee; border:2px solid #2d6a4f; color:#2d6a4f; font-weight:700; }

/* Feedback */
.fb-fail { background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; border-radius:8px; padding:9px 14px; font-size:0.85rem; margin-bottom:6px; }
.fb-pass { background:#e8f5ee; color:#2d6a4f; border:1px solid #74c69d; border-radius:8px; padding:9px 14px; font-size:0.85rem; margin-bottom:6px; }

/* Badges */
.badge-pass    { background:#e8f5ee; color:#2d6a4f; padding:4px 12px; border-radius:99px; font-size:0.75rem; font-weight:700; }
.badge-fail    { background:#fee2e2; color:#991b1b; padding:4px 12px; border-radius:99px; font-size:0.75rem; font-weight:700; }
.badge-refined { background:#fef3c7; color:#b45309; padding:4px 12px; border-radius:99px; font-size:0.75rem; font-weight:700; }

.sec-lbl { font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.09em; color:#6b6560; margin:14px 0 6px 0; }

/* JSON viewer */
.json-block { background:#1e1e2e; color:#cdd6f4; font-family:monospace; font-size:0.75rem;
    border-radius:10px; padding:14px 16px; overflow-x:auto; margin-top:6px; line-height:1.6; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="logo">📚 eklavya</div>', unsafe_allow_html=True)
st.markdown('<div class="tag">AI Content Pipeline — making learning accessible</div>', unsafe_allow_html=True)

# ── Pipeline Flow Diagram ─────────────────────────────────────────────────────
st.markdown("""
<div class="pipeline-flow">
  <div class="pf-node">
    <div class="icon">📥</div>
    <div class="lbl">Input</div>
    <div class="sub">Grade + Topic</div>
  </div>
  <div class="pf-arrow">→</div>
  <div class="pf-node">
    <div class="icon">⚙️</div>
    <div class="lbl">Generator</div>
    <div class="sub">Agent 1</div>
  </div>
  <div class="pf-arrow">→</div>
  <div class="pf-node">
    <div class="icon">🔍</div>
    <div class="lbl">Reviewer</div>
    <div class="sub">Agent 2</div>
  </div>
  <div class="pf-arrow">→</div>
  <div class="pf-node">
    <div class="icon">✨</div>
    <div class="lbl">Refine</div>
    <div class="sub">if fail (1×)</div>
  </div>
  <div class="pf-arrow">→</div>
  <div class="pf-node">
    <div class="icon">📤</div>
    <div class="lbl">Output</div>
    <div class="sub">Final Content</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Inputs ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 3])
with col1:
    grade = st.number_input("Grade", min_value=1, max_value=12, value=4)
with col2:
    topic = st.text_input("Topic", value="Types of angles")

st.markdown('<div style="color:#1a1814; font-weight:600; font-size:1rem; margin-bottom:-10px;">Show raw JSON output</div>', unsafe_allow_html=True)
show_json = st.toggle("Show raw JSON output", value=False, label_visibility="collapsed")
run = st.button("⚡ Generate Content", use_container_width=True, type="primary")


# ── Helpers ───────────────────────────────────────────────────────────────────
def render_content(data: dict):
    html = ""
    expl = data.get("explanation", "")
    if expl:
        html += '<div class="sec-lbl">Explanation</div>'
        html += f'<div class="expl">{expl}</div>'
        html += '<hr style="border:none;border-top:1px solid #e4e0d8;margin:14px 0">'

    mcqs = data.get("mcqs", [])
    if mcqs:
        html += '<div class="sec-lbl">Questions</div>'
        for i, q in enumerate(mcqs, 1):
            question_text = q.get("question", "")
            answer_key    = q.get("answer", "").strip().upper()
            options       = q.get("options", [])
            html += f'<div class="mcq"><div class="mcq-q">Q{i}. {question_text}</div><div>'
            for opt in options:
                opt_letter = opt.strip()[0].upper() if opt.strip() else ""
                cls = "opt-correct" if opt_letter == answer_key else "opt"
                html += f'<span class="{cls}">{opt}</span>'
            html += '</div></div>'

    st.markdown(html, unsafe_allow_html=True)


def render_review(data: dict):
    is_pass   = data.get("status", "").lower() == "pass"
    badge_cls = "badge-pass" if is_pass else "badge-fail"
    label     = "Content approved ✓" if is_pass else "Issues found — refinement triggered"
    fb_cls    = "fb-pass" if is_pass else "fb-fail"
    icon      = "✓" if is_pass else "⚠"

    html  = f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
    html += f'<span class="{badge_cls}">{data.get("status","").upper()}</span>'
    html += f'<span style="font-size:0.88rem;color:#6b6560">{label}</span></div>'
    for fb in data.get("feedback", []):
        html += f'<div class="{fb_cls}">{icon} {fb}</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_json_block(label: str, data: dict):
    if show_json:
        st.markdown(f'<div class="sec-lbl" style="margin-top:12px">Raw JSON — {label}</div>', unsafe_allow_html=True)
        st.json(data)


# ── Pipeline ──────────────────────────────────────────────────────────────────
if run:
    if not topic.strip():
        st.error("Please enter a topic.")
        st.stop()

    st.divider()

    with st.spinner("Running AI pipeline… this may take 10–20 seconds"):
        try:
            resp = requests.post(
                f"{BACKEND_URL}/generate",
                json={"grade": int(grade), "topic": topic},
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to backend. Start it with:")
            st.code("cd backend\nuvicorn main:app --reload", language="bash")
            st.stop()
        except requests.exceptions.HTTPError as e:
            try:
                detail = resp.json().get("detail", str(e))
            except Exception:
                detail = resp.text or str(e)
            st.error(f"❌ Backend error: {detail}")
            st.stop()
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
            st.stop()

    gen_data   = result.get("generated", {})
    rev_data   = result.get("review", {})
    is_pass    = rev_data.get("status", "").lower() == "pass"
    refinement = result.get("refinement_triggered", False)
    refined    = result.get("refined")

    # ── Step 1 ────────────────────────────────────────────────────────────────
    st.markdown('<div class="step-box s-green">⚙️ Step 1 — Generator Agent &nbsp; ✅ Done</div>', unsafe_allow_html=True)
    render_content(gen_data)
    show_json_block("Generator output", gen_data)

    st.divider()

    # ── Step 2 ────────────────────────────────────────────────────────────────
    s2_icon = "✅ Approved" if is_pass else "⚠️ Issues found"
    st.markdown(f'<div class="step-box s-blue">🔍 Step 2 — Reviewer Agent &nbsp; {s2_icon}</div>', unsafe_allow_html=True)
    render_review(rev_data)
    show_json_block("Reviewer output", rev_data)

    st.divider()

    # ── Step 3 ────────────────────────────────────────────────────────────────
    if refinement and refined:
        st.markdown('<div class="step-box s-amber">✨ Step 3 — Refinement + Final Output</div>', unsafe_allow_html=True)
        st.markdown('<span class="badge-refined">✦ Refined after review</span>', unsafe_allow_html=True)
        st.write("")
        render_content(refined)
        show_json_block("Refined output", refined)
    else:
        st.markdown('<div class="step-box s-done">✅ Step 3 — Final Output</div>', unsafe_allow_html=True)
        st.markdown('<span class="badge-pass">✓ Passed first review — no refinement needed</span>', unsafe_allow_html=True)
        st.write("")
        render_content(gen_data)

    st.success("🎉 Pipeline complete!")