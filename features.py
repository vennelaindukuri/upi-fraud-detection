"""One feature contract, used both to prepare training rows and live requests."""
from datetime import timedelta
import numpy as np
import pandas as pd
from config import FEATURE_COLUMNS


def feature_from_history(sender_id, receiver_id, amount, device_id, timestamp, history, receiver_risk=0.0):
    """Build behavior and velocity fields using only transactions before timestamp."""
    records = [dict(r) if not isinstance(r, dict) else r for r in history]
    prev = pd.DataFrame(records)
    if len(prev):
        prev["timestamp"] = pd.to_datetime(prev["timestamp"])
        times = prev.timestamp
        count_1h = int((times >= timestamp - timedelta(hours=1)).sum())
        count_24h = int((times >= timestamp - timedelta(hours=24)).sum())
        is_new_receiver = int(receiver_id not in set(prev.receiver_id))
        amounts = prev.amount.astype(float)
        mean = amounts.mean()
        std = amounts.std() if len(amounts) > 1 and amounts.std() > 0 else max(mean * .15, 1)
        dev = abs(float(amount) - mean) / std
        since = max(0, (timestamp - times.max()).total_seconds() / 60)
        is_new_device = int(device_id not in set(prev.device_id))
        relative_max = float(amount) / max(amounts.max(), 1)
    else:
        count_1h = count_24h = 0; is_new_receiver = is_new_device = 1
        dev = 0.; since = 1440.; relative_max = 1.
    return {
        "txn_count_last_1h": count_1h, "txn_count_last_24h": count_24h,
        "is_new_receiver": is_new_receiver, "amount_deviation": min(dev, 20),
        "time_since_last_txn": min(since, 43200), "hour_of_day": timestamp.hour,
        "is_odd_hour": int(timestamp.hour < 5), "is_new_device": is_new_device,
        "receiver_risk": receiver_risk, "amount": float(amount),
        "amount_relative_to_max": min(relative_max, 30),
    }


def build_training_features(df):
    """Chronological replay so training never sees future behavior."""
    df = df.copy(); df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    history, receiver_stats, output = {}, {}, []
    for row in df.itertuples(index=False):
        h = history.get(row.sender_id, [])
        stat = receiver_stats.get(row.receiver_id, [0, 0])
        risk = stat[1] / stat[0] if stat[0] else 0
        f = feature_from_history(row.sender_id, row.receiver_id, row.amount, row.device_id, row.timestamp, h, risk)
        output.append(f)
        history.setdefault(row.sender_id, []).append(row._asdict())
        receiver_stats.setdefault(row.receiver_id, [0, 0]); receiver_stats[row.receiver_id][0] += 1; receiver_stats[row.receiver_id][1] += int(row.is_fraud)
    return pd.DataFrame(output, columns=FEATURE_COLUMNS)
