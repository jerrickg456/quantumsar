#!/bin/sh
# Start the REST API in the background and the Streamlit UI in the foreground.
set -e
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
exec streamlit run app/streamlit_app.py --server.port "${PORT:-7860}" --server.address 0.0.0.0
