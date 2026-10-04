from __future__ import annotations

import streamlit as st


def configure_page() -> None:
    st.set_page_config(
        page_title="ContextFlow | Context to action",
        page_icon=":material/flowchart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
