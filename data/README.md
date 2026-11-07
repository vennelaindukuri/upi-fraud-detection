# Synthetic UPI Fraud Dataset (fully fictional)

All users, receivers and transactions are generated. IDs use the fake handle `@okshield` and a `.demo` marker.
Regenerate any time with `python generate_dataset.py` (seed = 42).

| File | Rows | What it is |
|---|---|---|
| transactions.csv | ~50.9k | One row per payment, with behavioural features and the fraud label (`is_fraud`) |
| users.csv | 200 | Sender profiles: typical amount, payments per day, active hours, devices |
| receivers.csv | 470 | Merchants, peers, suspicious (flagged) and mule accounts, with age and risk score |
| payee_recommendations.csv | ~1k | Top-5 suggested payees per sender (frequency + recency score) |

Period: 2026-07-01 to 2026-09-30 (a few late-night payments spill into 1 Oct). Fraud rate about 2.5 %.

## transactions.csv columns
- **Use as model features:** amount, hour, is_odd_hour, is_qr_payment, qr_mismatch, txn_count_1h, txn_count_24h,
  time_since_last_min, amount_zscore, amount_ratio, amount_vs_max, is_new_receiver, receiver_pay_count, is_new_device,
  receiver_risk_score, receiver_account_age_days (also day_of_week, is_weekend, avg_amount_hist if wanted).
- **Label:** `is_fraud` (1 = fraud).
- **Do NOT use as features (they reveal the answer):** txn_kind, fraud_type. Also skip txn_id, ids and names.
- Behavioural features are computed from the sender's PAST transactions only (no peeking at the future).
  For a sender's first few payments the baseline falls back to the typical amount from their profile.

## Fraud types (fraud_type)
account_takeover (new device, night, big amount) | amount_spike (sudden huge amount, e.g. Rs. 2,00,000) |
social_engineering (new scam receiver, amount well above normal) | burst (4-8 rapid payments) |
malicious_qr (QR with mismatched payee name, flagged receiver).

`txn_kind = legit_unusual` marks GENUINE payments that look odd (big purchase, new phone, travel, late night,
new young receiver). They exist so the OTP middle tier has real work to do.

## Honest limitation
This is synthetic data, so it is easier to separate than real UPI data. Say so in the report's Limitations section.
