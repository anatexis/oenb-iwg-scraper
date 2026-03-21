"""Minimal Streamlit frontend for the OeNB chatbot."""

from __future__ import annotations

from pathlib import Path

from analysis.rag_answering import run_rag_answering


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="OeNB Chatbot", layout="wide")
    st.title("OeNB Chatbot")
    query = st.text_input("Frage", placeholder="Wie hoch ist der Zinssatz für die Einlagenfazilität?")
    debug = st.checkbox("Debug anzeigen", value=False)

    if query:
        result = run_rag_answering(query, base_dir=Path.cwd(), debug=debug)
        st.subheader("Antwort")
        st.write(result.get("answer", ""))
        if result.get("citations"):
            st.subheader("Quellen")
            for citation in result["citations"]:
                st.write(citation["url"])
        if debug:
            st.subheader("Debug")
            st.json(result)


if __name__ == "__main__":
    main()
