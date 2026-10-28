"""Nawa Copilot — Streamlit demo.

    streamlit run app/streamlit_app.py

Pick a persona in the sidebar to see how answers (and what each person may see) change.
This is the demo front end; the production API + UI with real sign-in come in week 7.
"""
from __future__ import annotations

import html

import streamlit as st

from copilot.orchestrator import Copilot, Turn
from copilot.users import get_user

USD_THB = 33
AGENT_LABEL = {"knowledge": "📚 นโยบาย", "data": "🗄️ ข้อมูล", "calendar": "📅 ปฏิทิน",
               "summary": "🧾 สรุปเคส", "action": "🛠️ ทำรายการ"}

PERSONAS = {
    "NT0082": ("Ploy", "Data Engineer · พนักงาน", "employee"),
    "NT0197": ("Ton", "Sales Executive · พนักงานใหม่", "employee"),
    "NT0031": ("Nat", "Data Engineering Lead · หัวหน้าทีม", "team_lead"),
    "NT0048": ("Fon", "IT Support Specialist", "it_support"),
    "NT0061": ("Kwan", "HR Officer", "hr"),
    "NT0001": ("Aek", "CEO · ผู้บริหาร", "executive"),
}
EXAMPLES = {
    "NT0082": [("UC1 · วันลา + วันหยุดชดเชย", "ลาวันศุกร์ที่ 4 ธ.ค. แล้ววันจันทร์เป็นวันหยุดชดเชย นับลากี่วัน ฉันเหลือพอไหม"),
               ("UC2 · ไปสัมมนา", "จะไปสัมมนาที่เชียงใหม่ 3 วัน ต้องทำอะไรบ้าง"),
               ("SEC1 · ถามเงินเดือน", "เงินเดือนระดับ Team Lead เท่าไร"),
               ("SEC5 · สั่งปิด ticket", "ปิด ticket IT-1042 ให้หน่อย")],
    "NT0197": [("UC3 · แจ้งปัญหา + เปิด ticket", "notebook เปิดไม่ติดตั้งแต่เช้า ต้องแจ้งใคร ช่วยเปิดเรื่องให้หน่อย"),
               ("ทดลองงานลาได้ไหม", "ช่วงทดลองงานลาพักร้อนได้ไหม")],
    "NT0031": [("UC4 · ticket ทีม", "ทีมฉันมี ticket ค้างกี่ใบ อันไหนเกิน SLA"),
               ("วันลาลูกทีม", "ลูกทีมคนไหนเหลือวันลาพักร้อนไม่ถึง 3 วัน"),
               ("SEC2 · ข้อมูลทีมอื่น", "ทีม SMB Sales มี ticket ค้างกี่ใบ")],
    "NT0048": [("UC5 · สรุปเคส", "สรุปเคส IT-1042 และหาเคสเก่าที่คล้ายกันว่าแก้ยังไง"),
               ("ticket ที่ยังเปิด", "ตอนนี้มี ticket IT ที่ยังไม่ปิดกี่ใบ")],
    "NT0061": [("โครงสร้างเงินเดือน", "เงินเดือนระดับ Team Lead อยู่ที่เท่าไร"),
               ("พนักงานทดลองงาน", "ตอนนี้มีพนักงานที่อยู่ระหว่างทดลองงานกี่คน")],
    "NT0001": [("ภาพรวมองค์กร", "แผนกไหนมีพนักงานมากที่สุด"),
               ("โครงสร้างค่าตอบแทน", "ผู้บริหารได้โบนัสสูงสุดกี่เดือน")],
}

st.set_page_config(page_title="Nawa Copilot", page_icon="🧭", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stChatMessage, button, input, textarea { font-family: 'IBM Plex Sans Thai', sans-serif; }
.block-container { padding-top: 3.2rem; max-width: 980px; }
.nc-title { font-size: 2rem; font-weight: 600; line-height: 1.3; }
.nc-sub { color: #6b7280; margin-top: .1rem; margin-bottom: 1.2rem; }
.nc-chip { display: inline-block; padding: 2px 10px; margin: 2px 4px 2px 0; border-radius: 999px;
           background: rgba(37, 99, 235, .08); color: #1d4ed8; font-size: .82rem; border: 1px solid rgba(37,99,235,.18); }
.nc-src  { display: inline-block; padding: 2px 10px; margin: 2px 4px 2px 0; border-radius: 6px;
           background: rgba(16, 185, 129, .08); color: #047857; font-size: .8rem; border: 1px solid rgba(16,185,129,.2); }
.nc-meta { color: #6b7280; font-size: .78rem; margin-top: .35rem; }
.nc-pending { border: 1px solid #f59e0b; background: rgba(245, 158, 11, .07); border-radius: 10px; padding: .8rem 1rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="กำลังเตรียมระบบ (โหลดโมเดลค้นเอกสารครั้งแรกอาจใช้เวลาสักครู่)...")
def get_copilot() -> Copilot:
    return Copilot()


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("employee_id", "NT0082")
    ss.setdefault("messages", [])     # [{"role", "content", "turn": Turn | None}]
    ss.setdefault("pending", None)    # Turn waiting for confirmation
    ss.setdefault("show_trace", True)
    ss.setdefault("queued", None)


def reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.pending = None


def history() -> list[dict]:
    msgs = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    return msgs[-8:]


def render_meta(turn: Turn, show_trace: bool) -> None:
    if turn.agents:
        st.markdown("".join(f'<span class="nc-chip">{AGENT_LABEL.get(a, a)}</span>' for a in turn.agents),
                    unsafe_allow_html=True)
    if turn.sources:
        st.markdown("".join(f'<span class="nc-src">{html.escape(s)}</span>' for s in dict.fromkeys(turn.sources)),
                    unsafe_allow_html=True)
    st.markdown(f'<div class="nc-meta">{len(turn.usages)} LLM call(s) · ${turn.cost_usd:.5f} '
                f'≈ {turn.cost_usd * USD_THB:.2f} บาท</div>', unsafe_allow_html=True)
    if show_trace and turn.trace:
        with st.expander("ดูการทำงานเบื้องหลัง"):
            for step in turn.trace:
                st.markdown(f"- `{step}`")


def ask(question: str) -> None:
    user = get_user(st.session_state.employee_id)
    st.session_state.messages.append({"role": "user", "content": question, "turn": None})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🧭"):
        with st.spinner("กำลังคิด..."):
            turn = get_copilot().ask(question, user, history()[:-1])
        st.markdown(turn.answer)
        render_meta(turn, st.session_state.show_trace)
    st.session_state.messages.append({"role": "assistant", "content": turn.answer, "turn": turn})
    if turn.pending:
        st.session_state.pending = turn
    st.rerun()  # redraw everything from state (history, sidebar cost, confirm buttons)


def confirm(approved: bool) -> None:
    turn = st.session_state.pending
    st.session_state.pending = None
    with st.spinner("กำลังดำเนินการ..." if approved else "กำลังยกเลิก..."):
        done = get_copilot().confirm(turn, approved)
    st.session_state.messages.append({"role": "assistant", "content": done.action_outcome or "", "turn": None,
                                      "kind": "outcome"})


# ---------------- layout ----------------
init_state()
ss = st.session_state

with st.sidebar:
    st.markdown("### 👤 คุยในนาม")
    ids = list(PERSONAS)
    chosen = st.radio("persona", ids, index=ids.index(ss.employee_id), label_visibility="collapsed",
                      format_func=lambda i: f"{PERSONAS[i][0]} — {PERSONAS[i][1]}")
    if chosen != ss.employee_id:
        ss.employee_id = chosen
        reset_chat()
        st.rerun()
    st.caption(f"`{chosen}` · role `{PERSONAS[chosen][2]}` — สิทธิ์การเห็นข้อมูลต่างกันตาม role และผังองค์กร")

    st.markdown("### 💡 ลองถาม")
    for label, q in EXAMPLES.get(chosen, []):
        if st.button(label, key=f"ex-{chosen}-{label}", use_container_width=True, help=q):
            ss.queued = q

    st.divider()
    ss.show_trace = st.toggle("แสดงการทำงานเบื้องหลัง", value=ss.show_trace)
    total = sum(m["turn"].cost_usd for m in ss.messages if m.get("turn"))
    st.caption(f"ค่าใช้จ่ายบทสนทนานี้ ≈ {total * USD_THB:.2f} บาท")
    if st.button("🔄 เริ่มบทสนทนาใหม่", use_container_width=True):
        reset_chat()
        st.rerun()
    st.caption("ข้อมูลทั้งหมดเป็นบริษัทสมมติ Nawa Tech · Demo UI (week 4)")

st.markdown('<div class="nc-title">🧭 Nawa Copilot</div>', unsafe_allow_html=True)
st.markdown('<div class="nc-sub">ผู้ช่วย HR/IT ภายในองค์กร — ตอบจากนโยบายพร้อมอ้างอิง, ดูข้อมูลตามสิทธิ์, และทำรายการใน NawaDesk เมื่อคุณยืนยัน</div>',
            unsafe_allow_html=True)

if not ss.messages:
    name = PERSONAS[ss.employee_id][0]
    st.info(f"สวัสดีครับคุณ {name} 👋 ถามเรื่องวันลา นโยบาย การเดินทาง หรือปัญหา IT ได้เลย — หรือกดคำถามตัวอย่างทางซ้าย")

for m in ss.messages:
    with st.chat_message(m["role"], avatar="🧭" if m["role"] == "assistant" else None):
        if m.get("kind") == "outcome":
            (st.success if m["content"].startswith("✅") else st.warning)(m["content"])
        else:
            st.markdown(m["content"])
            if m.get("turn"):
                render_meta(m["turn"], ss.show_trace)

if ss.pending:
    p = ss.pending.pending
    with st.chat_message("assistant", avatar="🛠️"):
        st.markdown('<div class="nc-pending"><b>รอการยืนยันก่อนดำเนินการ</b><br>'
                    + html.escape(p["preview"]).replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("✅ ยืนยัน", type="primary", use_container_width=True):
            confirm(True)
            st.rerun()
        if c2.button("✖ ยกเลิก", use_container_width=True):
            confirm(False)
            st.rerun()

prompt = st.chat_input("พิมพ์คำถาม...", disabled=ss.pending is not None)
question = prompt or ss.queued
if question:
    ss.queued = None
    ask(question)
