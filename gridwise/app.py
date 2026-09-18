import streamlit as st

st.set_page_config(
    page_title="GridWise",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ GridWise")
st.subheader("Smart Campus 24-Hour Energy Planning")

notes = st.text_area(
    "Enter campus operation notes",
    height=200,
    placeholder="Example: Tomorrow is a working day. Keep the library open..."
)

if st.button("Generate 24-Hour Plan"):
    if not notes.strip():
        st.warning("Please enter operation notes.")
    else:
        st.info("Processing...")
        
        # Later we connect this to your FastAPI backend
        st.success("Plan generated.")