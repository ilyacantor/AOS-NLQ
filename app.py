import streamlit as st
import subprocess
import threading
import time
import os

st.set_page_config(
    page_title="aos-nlq | Natural Language Query",
    page_icon="generated-icon.png",
    layout="wide"
)

vite_process = None
vite_started = False

def start_vite():
    global vite_process, vite_started
    try:
        vite_process = subprocess.Popen(
            ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(3)
        vite_started = True
    except Exception as e:
        st.error(f"Failed to start Vite: {e}")

if "vite_thread" not in st.session_state:
    st.session_state.vite_thread = threading.Thread(target=start_vite, daemon=True)
    st.session_state.vite_thread.start()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@400;500;600;700&display=swap');
body, .stApp { 
    background-color: #020617; 
    font-family: 'Quicksand', sans-serif;
}
h1 {
    background: linear-gradient(135deg, #0bcad9, #2563eb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.info-box {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 2rem;
    margin: 2rem 0;
}
</style>
""", unsafe_allow_html=True)

st.title("aos-nlq")
st.markdown("### Natural Language Query Interface for Financial Data")

st.markdown("""
<div class="info-box">
<h4 style="color: #22d3ee;">Development Mode</h4>
<p style="color: #94a3b8;">
The React frontend is being served by Vite on port 5173.<br/>
This Streamlit wrapper is a temporary compatibility layer.
</p>
<p style="color: #64748b; margin-top: 1rem;">
<strong>Project Status:</strong> Awaiting test data upload and DCLv2 endpoint configuration
</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="info-box">
    <h4 style="color: #4ade80;">Database</h4>
    <p style="color: #94a3b8;">Supabase PostgreSQL connected</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="info-box">
    <h4 style="color: #60a5fa;">DCL Status</h4>
    <p style="color: #94a3b8;">Awaiting endpoint configuration</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="info-box">
    <h4 style="color: #a855f7;">Test Data</h4>
    <p style="color: #94a3b8;">Pending upload</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.markdown("""
<p style="color: #64748b; text-align: center;">
aos-nlq | Natural Language Query Engine | Dev Mode
</p>
""", unsafe_allow_html=True)
