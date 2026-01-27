import streamlit as st
import pandas as pd
import os
from datetime import datetime

st.set_page_config(
    page_title="aos-nlq | Natural Language Query",
    page_icon="generated-icon.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@300;400;500;600;700&display=swap');

:root {
    --cyan-400: #22d3ee;
    --cyan-500: #0bcad9;
    --cyan-600: #0891b2;
    --green-400: #4ade80;
    --green-500: #22c55e;
    --blue-400: #60a5fa;
    --blue-500: #3b82f6;
    --blue-600: #2563eb;
    --purple-400: #c084fc;
    --purple-500: #a855f7;
    --red-400: #f87171;
    --red-500: #ef4444;
    --slate-400: #94a3b8;
    --slate-500: #64748b;
    --slate-600: #475569;
    --slate-700: #334155;
    --slate-800: #1e293b;
    --slate-900: #0f172a;
    --slate-950: #020617;
}

html, body, [class*="css"] {
    font-family: 'Quicksand', sans-serif !important;
}

.stApp {
    background-color: var(--slate-950);
}

.main-header {
    background: linear-gradient(135deg, var(--cyan-500), var(--blue-600));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.5rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}

.sub-header {
    color: var(--slate-400);
    font-size: 1.1rem;
    margin-bottom: 2rem;
}

.card {
    background-color: rgba(30, 41, 59, 0.6);
    border: 1px solid var(--slate-700);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.status-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-active {
    background-color: rgba(34, 197, 94, 0.2);
    color: var(--green-400);
}

.status-pending {
    background-color: rgba(234, 179, 8, 0.2);
    color: #facc15;
}

.status-error {
    background-color: rgba(239, 68, 68, 0.2);
    color: var(--red-400);
}

.query-input {
    background-color: var(--slate-800) !important;
    border: 1px solid var(--slate-600) !important;
    color: white !important;
    border-radius: 8px !important;
}

.stTextArea textarea {
    background-color: rgba(30, 41, 59, 0.8) !important;
    border: 1px solid var(--slate-600) !important;
    color: white !important;
    font-family: 'Quicksand', sans-serif !important;
}

.stButton > button {
    background: linear-gradient(135deg, var(--cyan-500), var(--blue-600)) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Quicksand', sans-serif !important;
    font-weight: 600 !important;
    padding: 0.5rem 2rem !important;
    transition: all 0.3s ease !important;
}

.stButton > button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

.sidebar .stMarkdown {
    color: var(--slate-400);
}

div[data-testid="stSidebar"] {
    background-color: var(--slate-900);
}

.history-item {
    background-color: rgba(30, 41, 59, 0.4);
    border: 1px solid var(--slate-700);
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
    cursor: pointer;
}

.history-item:hover {
    border-color: var(--cyan-500);
}

.result-table {
    background-color: rgba(30, 41, 59, 0.6);
    border-radius: 8px;
    overflow: hidden;
}

.dcl-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background-color: rgba(30, 41, 59, 0.6);
    border-radius: 8px;
    border: 1px solid var(--slate-700);
}

.pulse {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "dcl_connected" not in st.session_state:
    st.session_state.dcl_connected = False

with st.sidebar:
    st.markdown("### DCL Connection")
    
    dcl_endpoint = st.text_input(
        "DCLv2 Endpoint URL",
        placeholder="https://api.dcl.example.com/v2",
        help="Enter the DCLv2 data unification engine endpoint"
    )
    
    if dcl_endpoint:
        st.session_state.dcl_connected = True
        st.markdown(
            '<div class="dcl-status">'
            '<span style="color: #4ade80;">●</span>'
            '<span style="color: #94a3b8;">DCL Ready</span>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="dcl-status">'
            '<span style="color: #64748b;">●</span>'
            '<span style="color: #64748b;">No endpoint configured</span>'
            '</div>',
            unsafe_allow_html=True
        )
    
    st.markdown("---")
    st.markdown("### Query History")
    
    if st.session_state.query_history:
        for i, item in enumerate(reversed(st.session_state.query_history[-10:])):
            with st.container():
                st.markdown(
                    f'<div class="history-item">'
                    f'<div style="color: #22d3ee; font-size: 0.85rem;">{item["query"][:50]}...</div>'
                    f'<div style="color: #64748b; font-size: 0.7rem;">{item["timestamp"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
    else:
        st.markdown(
            '<p style="color: #64748b; font-size: 0.85rem;">No queries yet</p>',
            unsafe_allow_html=True
        )

st.markdown('<h1 class="main-header">aos-nlq</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Natural Language Query Interface for Financial Data | Powered by DCLv2</p>',
    unsafe_allow_html=True
)

col1, col2 = st.columns([3, 1])

with col1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    query_input = st.text_area(
        "Enter your query",
        placeholder="Ask a question about your financial data...\n\nExamples:\n- Show me revenue trends for Q4 2024\n- What are the top performing assets?\n- Compare expense categories year over year",
        height=120,
        label_visibility="collapsed"
    )
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])
    
    with col_btn1:
        submit_btn = st.button("Query", type="primary", use_container_width=True)
    
    with col_btn2:
        clear_btn = st.button("Clear", use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Status**")
    
    if st.session_state.dcl_connected:
        st.markdown(
            '<span class="status-badge status-active">DCL Connected</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<span class="status-badge status-pending">Awaiting Config</span>',
            unsafe_allow_html=True
        )
    
    st.markdown(f"**Queries:** {len(st.session_state.query_history)}")
    st.markdown('</div>', unsafe_allow_html=True)

if submit_btn and query_input:
    st.session_state.query_history.append({
        "query": query_input,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending"
    })
    
    with st.spinner("Processing query via DCLv2..."):
        st.info("DCLv2 endpoint not configured. Test data will be available after upload.")
        
        st.session_state.current_result = {
            "query": query_input,
            "status": "pending",
            "message": "Awaiting DCLv2 connection and test data"
        }

if clear_btn:
    st.session_state.current_result = None
    st.rerun()

st.markdown("---")
st.markdown("### Results")

if st.session_state.current_result:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    
    result = st.session_state.current_result
    
    if result.get("status") == "pending":
        st.markdown(
            f'<p style="color: #facc15;">⏳ {result.get("message", "Processing...")}</p>',
            unsafe_allow_html=True
        )
    elif result.get("status") == "success":
        if "data" in result:
            st.dataframe(result["data"], use_container_width=True)
    elif result.get("status") == "error":
        st.markdown(
            f'<p style="color: #f87171;">❌ {result.get("message", "Error occurred")}</p>',
            unsafe_allow_html=True
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="card">'
        '<p style="color: #64748b; text-align: center;">Enter a query above to get started</p>'
        '</div>',
        unsafe_allow_html=True
    )

st.markdown("---")
st.markdown(
    '<p style="color: #64748b; text-align: center; font-size: 0.8rem;">'
    'aos-nlq | Natural Language Query Engine | Dev Mode'
    '</p>',
    unsafe_allow_html=True
)
