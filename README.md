# REDFLAG — Real-Time UPI Fraud Detection AI

A college mini-project prototype that scores synthetic UPI payments from live sender history and responds with **ALLOW**, **OTP VERIFY**, or **BLOCK**. The OTP middle tier limits both unnecessary blocks and missed fraud.

## Run locally

```bash
python -m pip install -r requirements.txt
python seed_from_dataset.py   # load the fictional dataset into SQLite
python train_models.py        # time-split training (first 80%, last 15% of it held for thresholds)
python evaluate.py            # writes reports/comparison.csv, decision_mix.csv, roc.png, pr_curve.png
python app.py
```

On macOS you can also double-click `run.command` (starts the app) or `eval.command` (re-runs the evaluation).

Open `http://127.0.0.1:5001`. The landing page (`/`) has the animated hero; **Make a transaction** opens the app (`/app`).

## App flow

1. **Sender** – pick one of seven demo accounts.
2. **Payment** – enter a receiver (`…@okshield`), pick from Recent / suggested payees, or upload a QR. Toggle day/night and usual/new phone.
3. **Scanning** → **Result** – risk score, top reasons and engine details. Allowed payments can be completed; OTP payments show a simulated SMS (60 s, 3 attempts); blocked payments can be reported.
4. **Scenarios** – one click runs: everyday payment (Allow), college fees (Verify), refund-support scam (Verify), ₹2 lakh spike (Block), 2 AM takeover (Block), and a rapid burst (Verify → Block).
5. **Dashboard** – live decision mix, latency, the activity feed, and the model's held-out results read from `reports/comparison.csv`.
6. **Attack mode** – play the fraudster: pick a victim, a mule account, amount, time and phone, and try to drain the account. OTP challenges count as stopped (the code goes to the victim).
7. **History** – per-account view of everything tried in the demo plus recorded payments (fraud rows labelled).
8. **How it works** – the pipeline, the held-out metrics, decision mix, ROC / PR charts and limitations, all read from `reports/`.
9. **Demo QR codes** (`/demo-qr`) – download a code and upload it under Scan QR; the tampered ones are flagged before payment.

API: `/predict`, `/verify_otp`, `/confirm`, `/scan_qr`, `/users`, `/history/<user>`, `/recommend/<user>`, `/scenarios`, `/admin/stats`, `/admin/model`, `/admin/reset_live`.

Every result also shows **Why this score** (each signal's contribution, measured by resetting it to a typical genuine value and re-scoring), **Compared to usual** (the sender's last 30 genuine payments vs this one) and a **What if…** panel that re-scores live as you drag the amount or flip time/device. Scenarios has **▶ Play the story**, a narrated autoplay of all six cases. A tampered QR shows a full-screen warning; paying anyway always requires a one-time code.

## Design notes

`dataset_features.py` is the feature contract shared by training and live scoring. The risk score blends a calibrated random forest (70%) with an autoencoder anomaly score trained only on genuine payments (30%). Every scored attempt is logged, and unfinished attempts count toward the 1 h / 24 h velocity features; a **velocity guard** rule blocks a sender once three unfinished attempts in an hour are already rated risky, which is what turns a rapid burst into a block. A mismatched QR is never allowed without a code, and a watch-listed receiver's risk score sets a floor (30% of it) under the model — the result page says when that floor was applied.

## Limitations

All transactions and OTP delivery are simulated, and the synthetic data is easier to separate than real UPI data. A production system needs authenticated identities, encrypted data, real device telemetry, monitoring, fairness checks, model governance, secure OTP delivery, and human-review flows. This prototype is not a payment processor or security product.
