import streamlit as st
import requests

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Eklavya — AI Content Pipeline V2",
    page_icon="📚",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,600;1,400&family=DM+Sans:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.logo { font-family:'Fraunces',serif; font-size:3.5rem; color:#2d6a4f; }
.tag  { color:#6b6560; font-size:0.85rem; margin-top:-8px; margin-bottom:1rem; }
.pipeline-flow { display:flex; align-items:center; justify-content:center; gap:0; background:#f7f5f0; border:1px solid #e4e0d8; border-radius:12px; padding:14px 16px; margin-bottom:1.5rem; flex-wrap:wrap; }
.pf-node { display:flex; flex-direction:column; align-items:center; background:#fff; border:1px solid #e4e0d8; border-radius:10px; padding:8px 12px; min-width:90px; text-align:center; margin:3px; }
.pf-node .icon { font-size:1.2rem; margin-bottom:3px; }
.pf-node .lbl  { font-size:0.65rem; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:#2d6a4f; }
.pf-node .sub  { font-size:0.6rem; color:#6b6560; margin-top:1px; }
.pf-arrow { font-size:1rem; color:#b0a99f; padding:0 4px; }
.step-box { padding:11px 16px; border-radius:10px; margin:6px 0 4px 0; font-weight:600; font-size:0.82rem; text-transform:uppercase; letter-spacing:0.07em; }
.s-green { background:#e8f5ee; color:#2d6a4f; border-left:4px solid #2d6a4f; }
.s-blue  { background:#dbeafe; color:#1e40af; border-left:4px solid #1e40af; }
.s-amber { background:#fef3c7; color:#b45309; border-left:4px solid #d97706; }
.s-purple{ background:#f3e8ff; color:#6b21a8; border-left:4px solid #9333ea; }
.s-done  { background:#e8f5ee; color:#2d6a4f; border-left:4px solid #2d6a4f; }
.s-red   { background:#fee2e2; color:#991b1b; border-left:4px solid #dc2626; }
.expl { font-size:0.95rem; line-height:1.75; background:#f7f5f0; padding:14px 18px; border-radius:10px; border:1px solid #e4e0d8; color:#1e1e1e; }
.tnote { font-size:0.85rem; line-height:1.65; background:#fef9ee; padding:12px 16px; border-radius:10px; border:1px solid #fde68a; color:#1e1e1e; }
.mcq  { border:1px solid #e4e0d8; border-radius:10px; padding:13px 15px; margin-bottom:9px; background:#fafaf8; color:#1e1e1e; }
.mcq-q { font-weight:600; font-size:0.88rem; margin-bottom:9px; }
.opt         { display:inline-block; padding:4px 12px; border-radius:99px; font-size:0.8rem; margin:3px; border:1px solid #e4e0d8; background:#fff; color:#1e1e1e; }
.opt-correct { display:inline-block; padding:4px 12px; border-radius:99px; font-size:0.8rem; margin:3px; background:#e8f5ee; border:2px solid #2d6a4f; color:#2d6a4f; font-weight:700; }
.score-row { display:flex; align-items:center; gap:10px; margin-bottom:7px; }
.score-lbl { font-size:0.78rem; color:#6b6560; width:160px; flex-shrink:0; }
.score-bar-bg { flex:1; height:8px; background:#e4e0d8; border-radius:99px; overflow:hidden; }
.score-bar    { height:100%; border-radius:99px; }
.score-val { font-size:0.78rem; font-weight:600; width:24px; text-align:right; }
.fb-fail { background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; border-radius:8px; padding:8px 13px; font-size:0.82rem; margin-bottom:5px; }
.fb-pass { background:#e8f5ee; color:#2d6a4f; border:1px solid #74c69d; border-radius:8px; padding:8px 13px; font-size:0.82rem; margin-bottom:5px; }
.fb-field { font-family:monospace; font-size:0.75rem; background:#fff; padding:1px 5px; border-radius:4px; border:1px solid #e4e0d8; margin-right:5px; }
.tag-grid { display:grid; grid-template-columns:1fr 1fr; gap:7px; }
.tag-item { background:#f7f5f0; border:1px solid #e4e0d8; border-radius:8px; padding:8px 12px; color:#1e1e1e; }
.tag-key  { font-size:0.68rem; text-transform:uppercase; letter-spacing:0.06em; color:#6b6560; margin-bottom:2px; }
.tag-val  { font-size:0.85rem; font-weight:500; }
.badge-approved { background:#e8f5ee; color:#2d6a4f; padding:3px 11px; border-radius:99px; font-size:0.72rem; font-weight:700; }
.badge-rejected { background:#fee2e2; color:#991b1b; padding:3px 11px; border-radius:99px; font-size:0.72rem; font-weight:700; }
.badge-refined  { background:#fef3c7; color:#b45309; padding:3px 11px; border-radius:99px; font-size:0.72rem; font-weight:700; }
.run-meta { font-size:0.75rem; color:#6b6560; margin-bottom:6px; }
.sec-lbl { font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.09em; color:#6b6560; margin:12px 0 5px 0; }
.threshold-note { font-size:0.75rem; color:#6b6560; background:#f7f5f0; border:1px solid #e4e0d8; border-radius:8px; padding:7px 12px; margin-bottom:10px; }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="logo">📚 eklavya</div>', unsafe_allow_html=True)
st.markdown('<div class="tag">Governed AI Content Pipeline v2 — auditable, schema-validated</div>', unsafe_allow_html=True)

# ── Pipeline Flow ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="pipeline-flow">
  <div class="pf-node"><div class="icon">📥</div><div class="lbl">Input</div><div class="sub">Grade + Topic</div></div>
  <div class="pf-arrow">→</div>
  <div class="pf-node"><div class="icon">⚙️</div><div class="lbl">Generator</div><div class="sub">Agent 1</div></div>
  <div class="pf-arrow">→</div>
  <div class="pf-node"><div class="icon">🔍</div><div class="lbl">Reviewer</div><div class="sub">Scores 1–5</div></div>
  <div class="pf-arrow">→</div>
  <div class="pf-node"><div class="icon">🔁</div><div class="lbl">Refiner</div><div class="sub">max 2×</div></div>
  <div class="pf-arrow">→</div>
  <div class="pf-node"><div class="icon">🏷️</div><div class="lbl">Tagger</div><div class="sub">if approved</div></div>
  <div class="pf-arrow">→</div>
  <div class="pf-node"><div class="icon">📦</div><div class="lbl">RunArtifact</div><div class="sub">audit trail</div></div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_generate, tab_history = st.tabs(["⚡ Generate", "📋 History"])


# ── Helpers ────────────────────────────────────────────────────────────────────
def score_color(v):
    if v >= 4: return "#2d6a4f"
    if v >= 3: return "#d97706"
    return "#dc2626"

def score_bar_width(v):
    return int((v / 5) * 100)

def render_content(data: dict, label=""):
    html = ""
    expl = data.get("explanation", {})
    expl_text = expl.get("text", "") if isinstance(expl, dict) else str(expl)
    if expl_text:
        html += '<div class="sec-lbl">Explanation</div>'
        html += f'<div class="expl">{expl_text}</div>'

    tn = data.get("teacher_notes", {})
    if tn:
        lo   = tn.get("learning_objective", "")
        misc = tn.get("common_misconceptions", [])
        html += '<div class="sec-lbl" style="margin-top:10px">Teacher Notes</div>'
        html += f'<div class="tnote"><b>Learning objective:</b> {lo}'
        if misc:
            html += '<br><b>Common misconceptions:</b><ul style="margin:4px 0 0 16px">'
            for m in misc: html += f'<li style="font-size:0.83rem">{m}</li>'
            html += '</ul>'
        html += '</div>'

    mcqs = data.get("mcqs", [])
    if mcqs:
        html += '<div class="sec-lbl" style="margin-top:10px">Questions</div>'
        for i, q in enumerate(mcqs, 1):
            q_text   = q.get("question", "")
            ci       = q.get("correct_index", -1)
            options  = q.get("options", [])
            html += f'<div class="mcq"><div class="mcq-q">Q{i}. {q_text}</div><div>'
            for j, opt in enumerate(options):
                cls   = "opt-correct" if j == ci else "opt"
                html += f'<span class="{cls}">{opt}</span>'
            html += '</div></div>'

    st.markdown(html, unsafe_allow_html=True)


def render_review(data: dict):
    scores  = data.get("scores", {})
    passed  = data.get("passed", False)
    feedback= data.get("feedback", [])

    dims = [
        ("Age appropriateness", "age_appropriateness"),
        ("Correctness",         "correctness"),
        ("Clarity",             "clarity"),
        ("Coverage",            "coverage"),
    ]
    html = '<div class="threshold-note">Pass threshold: <b>correctness ≥ 4</b> AND <b>average ≥ 3.5</b></div>'
    for lbl, key in dims:
        v = scores.get(key, 0)
        c = score_color(v)
        w = score_bar_width(v)
        html += f'''<div class="score-row">
          <div class="score-lbl">{lbl}</div>
          <div class="score-bar-bg"><div class="score-bar" style="width:{w}%;background:{c}"></div></div>
          <div class="score-val" style="color:{c}">{v}/5</div>
        </div>'''

    avg = sum(scores.get(k, 0) for _, k in dims) / 4
    html += f'<div style="font-size:0.78rem;color:#6b6560;margin:6px 0 10px">Average: <b>{avg:.2f}</b> — <b>{"PASS ✓" if passed else "FAIL ✗"}</b></div>'

    fb_cls = "fb-pass" if passed else "fb-fail"
    for fb in feedback:
        field = fb.get("field", "")
        issue = fb.get("issue", "")
        icon  = "✓" if passed else "⚠"
        html += f'<div class="{fb_cls}"><span class="fb-field">{field}</span>{icon} {issue}</div>'

    st.markdown(html, unsafe_allow_html=True)


def render_tags(tags: dict):
    if not tags: return
    html = '<div class="tag-grid">'
    items = [
        ("Subject",      tags.get("subject", "")),
        ("Topic",        tags.get("topic", "")),
        ("Difficulty",   tags.get("difficulty", "")),
        ("Bloom's Level",tags.get("blooms_level", "")),
        ("Grade",        str(tags.get("grade", ""))),
        ("Content Type", ", ".join(tags.get("content_type", []))),
    ]
    for k, v in items:
        html += f'<div class="tag-item"><div class="tag-key">{k}</div><div class="tag-val">{v}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ── Generate Tab ────────────────────────────────────────────────────────────────
with tab_generate:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1: grade   = st.number_input("Grade", min_value=1, max_value=12, value=4)
    with col2: topic   = st.text_input("Topic", value="Types of angles")
    with col3: user_id = st.text_input("User ID", value="demo_user")

    show_json = st.toggle("Show raw RunArtifact JSON", value=False)
    run       = st.button("⚡ Generate Content", use_container_width=True, type="primary")

    if run:
        if not topic.strip():
            st.error("Please enter a topic.")
            st.stop()

        st.divider()
        with st.spinner("Running governed pipeline… may take 20–40s"):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/generate",
                    json={"grade": int(grade), "topic": topic, "user_id": user_id},
                    timeout=180,
                )
                resp.raise_for_status()
                result = resp.json()
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to backend.")
                st.code("cd backend\\nuvicorn main:app --reload", language="bash")
                st.stop()
            except requests.exceptions.HTTPError:
                st.error(f"❌ Backend error: {resp.json().get('detail', 'Unknown error')}")
                st.stop()
            except Exception as e:
                st.error(f"❌ {e}")
                st.stop()

        attempts  = result.get("attempts", [])
        final     = result.get("final", {})
        run_id    = result.get("run_id", "")
        ts        = result.get("timestamps", {})
        is_approved = final.get("status") == "approved"

        st.markdown(f'<div class="run-meta">run_id: <code>{run_id}</code> · {len(attempts)} attempt(s) · started: {ts.get("started_at","")[:19]}</div>', unsafe_allow_html=True)

        # Show each attempt
        for attempt in attempts:
            n      = attempt.get("attempt", 1)
            passed = attempt.get("passed", False)
            draft  = attempt.get("draft", {})
            review = attempt.get("review", {})

            prefix = "Initial" if n == 1 else f"Refinement {n-1}"
            color  = "s-green" if passed else "s-amber"

            st.markdown(f'<div class="step-box s-green">⚙️ {prefix} — Generator</div>', unsafe_allow_html=True)
            render_content(draft)

            icon2  = "✅ Passed" if passed else "⚠️ Failed"
            st.markdown(f'<div class="step-box s-blue">🔍 {prefix} — Reviewer &nbsp; {icon2}</div>', unsafe_allow_html=True)
            render_review(review)
            st.divider()

        # Final result
        if is_approved:
            st.markdown('<div class="step-box s-purple">🏷️ Tagger Agent — content classified</div>', unsafe_allow_html=True)
            render_tags(final.get("tags", {}))
            st.divider()
            st.markdown('<div class="step-box s-done">✅ Final Output — Approved</div>', unsafe_allow_html=True)
            st.markdown('<span class="badge-approved">✓ Approved</span>', unsafe_allow_html=True)
            st.write("")
            render_content(final.get("content", {}))
        else:
            st.markdown('<div class="step-box s-red">❌ Final Status — Rejected</div>', unsafe_allow_html=True)
            st.error("Content could not meet quality thresholds after maximum refinement attempts.")

        if show_json:
            st.markdown('<div class="sec-lbl" style="margin-top:14px">Full RunArtifact JSON</div>', unsafe_allow_html=True)
            st.json(result)

        st.success(f"🎉 Pipeline complete — status: {final.get('status','').upper()}")


# ── History Tab ─────────────────────────────────────────────────────────────────
with tab_history:
    st.markdown("### Past Pipeline Runs")
    filter_user = st.text_input("Filter by User ID (leave blank for all)", value="")
    load_btn    = st.button("Load History", type="secondary")

    if load_btn:
        try:
            params = {"user_id": filter_user} if filter_user.strip() else {}
            resp   = requests.get(f"{BACKEND_URL}/history", params=params, timeout=30)
            resp.raise_for_status()
            history = resp.json()
        except Exception as e:
            st.error(f"❌ Could not load history: {e}")
            st.stop()

        total     = history.get("total", 0)
        artifacts = history.get("artifacts", [])
        st.markdown(f"**{total} run(s) found**")

        for art in artifacts:
            run_id   = art.get("run_id", "")[:8]
            inp      = art.get("input", {})
            final    = art.get("final", {})
            ts       = art.get("timestamps", {})
            status   = final.get("status", "unknown")
            attempts = len(art.get("attempts", []))
            badge    = "badge-approved" if status == "approved" else "badge-rejected"

            with st.expander(f"[{run_id}] Grade {inp.get('grade')} — {inp.get('topic')} · {attempts} attempt(s) · {ts.get('started_at','')[:10]}"):
                st.markdown(f'<span class="{badge}">{status.upper()}</span>', unsafe_allow_html=True)
                tags = final.get("tags")
                if tags:
                    st.markdown(f"**Bloom's:** {tags.get('blooms_level')} · **Difficulty:** {tags.get('difficulty')} · **Subject:** {tags.get('subject')}")
                st.json(art)