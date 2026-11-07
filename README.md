# REDFLAG — Real-Time UPI Fraud Detection AI

A college mini-project prototype that scores every UPI payment at the moment it is made, using the sender's own payment history, and responds with **ALLOW**, **OTP VERIFY** or **ON HOLD**. The OTP middle tier cuts both missed fraud and unnecessary blocks: a genuine user making an unusual payment can pass a one-time code, a fraudster with only a stolen login cannot.

All users, receivers and transactions are fictional (`@okshield` handles); no real payment network or personal data is involved.

## Run locally

```bash
python -m pip install -r requirements.txt
python seed_from_dataset.py   # load the synthetic dataset into SQLite (creates upi_fraud.db)
python train_models.py        # time-split training; saves models/artifacts/fraud_model.joblib
python evaluate.py            # optional: rewrites reports/ (comparison, decision mix, ROC, PR curve)
python app.py
```

Open `http://127.0.0.1:5001`. The landing page (`/`) has the animated hero; **Make a transaction** opens the app (`/app`).

On macOS you can also double-click `run.command` (starts the app), `retrain.command` or `eval.command`.

> `upi_fraud.db` and the trained model are not in the repo (they are large and fully reproducible) — run the first three commands once after cloning.

## The app

- **Pay** – pick a demo sender (or create a new user), then enter a UPI ID, pick a recent payee or scan a QR code. A card shows what you have paid that receiver before, and a line shows how much of the ₹1,00,000 daily UPI limit is left. Toggle day/night and usual/new phone to simulate unusual conditions.
- **Result** – decision, risk score, scoring time and the top reasons. Allowed payments can be completed; OTP payments show a simulated SMS (60 s, 3 attempts); payments on hold can be reported, or the owner can continue once by verifying a fresh code sent to the registered phone.
- **Why this score / Compared to usual / What if…** – each signal's contribution (occlusion: reset it to a typical genuine value and re-score), this payment against the sender's last 30 genuine payments, and live re-scoring as you drag the amount or flip time/device.
- **Tampered QR** – a QR whose name doesn't match the registered UPI ID gets a full-screen warning before paying; paying anyway always requires a code. Demo codes: `/demo-qr`.
- **Attack** – play the fraudster: pick a victim, a mule or flagged account, amount, time and phone, and try to drain the account. OTP challenges count as stopped (the code goes to the victim).
- **History** – per-account view of everything tried in the demo plus recorded payments, with known fraud labelled.

## How scoring works

- `dataset_features.py` is the feature contract shared by training and live scoring: 16 behavioural, velocity and receiver features built only from the sender's past payments.
- **Model:** a calibrated Random Forest (70%) blended with an autoencoder anomaly score trained only on genuine payments (30%, on log-scaled inputs). The anomaly part is gated — it only adds risk once the forest finds a payment at least slightly suspicious, so a genuine large payment from your own phone isn't penalised just for being unusual.
- **Thresholds:** risk < 0.25 → ALLOW, 0.25–0.70 → OTP VERIFY, > 0.70 → ON HOLD.
- **Safety rules on top of the model:**
  - *Velocity guard* – 3+ unfinished attempts in an hour that the model already finds risky → on hold (turns a rapid burst into a hold).
  - *Takeover guard* – new phone + before 6 AM + ≥ 5× the usual amount → on hold.
  - *Pair guard* – a large payment is only normal if you've paid this receiver similar amounts before; somewhat above → OTP, far above or to a new/unverified account → on hold.
  - *QR step-up* – a mismatched QR is never allowed without a code.
  - *Receiver floor* – a watch-listed receiver never scores below 30% of its risk score (the engine details say when this applied).
  - *Daily limit* – ₹1,00,000 per sender per day.

## Results (time-based hold-out: most recent 20%, 10,303 payments)

| System | Precision | Recall | F1 | False blocks | Missed fraud |
|---|---|---|---|---|---|
| Static rules | 0.306 | 0.486 | 0.376 | 281 | 131 |
| ML allow/block | 0.969 | 0.867 | 0.915 | 7 | 34 |
| **ML + OTP tier** | **0.987** | **0.914** | **0.949** | **3** | **22** |

ROC-AUC 0.997, PR-AUC 0.962. Scoring takes roughly 75–110 ms per payment on a laptop. Full output in `reports/`.

## API

`/predict`, `/verify_otp`, `/step_up`, `/confirm`, `/scan_qr`, `/qr_options`, `/whatif`, `/pair_stats`, `/users` (GET, POST), `/history/<user>`, `/recommend/<user>`, `/profile/<user>`, `/activity/<user>`, `/scenarios`, `/admin/stats`, `/admin/model`, `/admin/reset_live`.

## Project layout

```
app.py                  Flask API, safety rules, OTP / step-up, QR checks
config.py               thresholds, weights, feature list
dataset_features.py     shared feature contract, autoencoder input, gated blend
train_models.py         Random Forest + autoencoder training
evaluate.py             hold-out evaluation and charts -> reports/
seed_from_dataset.py    CSVs -> SQLite
generate_qr.py          genuine and tampered demo QR codes
data/                   synthetic dataset and its generator
templates/, static/     web interface
reports/                evaluation results
```

## Limitations

All transactions and OTP delivery are simulated, and the synthetic data is easier to separate than real UPI data. Social-engineering fraud (the victim pays from their own phone) is the hardest case and makes up most of the missed fraud. A production system would need real device telemetry, authenticated identities, encrypted data, secure OTP delivery, monitoring, fairness checks and human review. This prototype is not a payment processor or security product.
