#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
echo "Starting UPI Shield at http://127.0.0.1:5001 ..."
(sleep 4; open http://127.0.0.1:5001) &
python app.py
