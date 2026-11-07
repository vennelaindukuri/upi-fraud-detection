#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
echo "== 1/4 Regenerating dataset (v2: genuine large payments)"
(cd data && python generate_dataset.py)
echo "== 2/4 Loading into SQLite"
python seed_from_dataset.py
echo "== 3/4 Training models"
python train_models.py 2>&1 | grep -v -i warning
echo "== 4/4 Evaluating on the held-out 20%"
python evaluate.py 2>&1 | grep -v -i warning | tee reports/evaluation.txt
echo
touch app.py   # makes the running app reload the new model
echo "DONE. The app reloads the new model automatically (refresh the browser)."
