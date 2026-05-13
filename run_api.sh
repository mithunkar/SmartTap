#!/bin/bash

set -e

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "Starting SmartTap API at http://localhost:8000"
uvicorn smarttap_api:app --reload --host 127.0.0.1 --port 8000
