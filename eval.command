#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
echo "Evaluating the model on the held-out 20% of transactions..."
python evaluate.py 2>&1 | grep -v -i warning | tee reports/evaluation.txt
echo
echo "Saved to reports/  (you can close this window)"
