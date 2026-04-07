#!/bin/bash

set -e

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "Starting SmartTap UI at http://localhost:8501"
streamlit run smarttap_ui.py
