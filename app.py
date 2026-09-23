"""Task 3.2: rescue dashboard. AI inference belongs to the team's backend."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="CAM AI · Cứu hộ", page_icon="🌊", layout="wide")
st.markdown("<style>.block-container{padding:0;max-width:100%}header{visibility:hidden}</style>", unsafe_allow_html=True)
components.html((Path(__file__).parent / "frontend/index.html").read_text(encoding="utf-8"), height=1050, scrolling=True)
