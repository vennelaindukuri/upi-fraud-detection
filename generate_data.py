"""Generate realistic-but-synthetic UPI history. No real payment data is used."""
import random, uuid
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from config import DATA_PATH, RANDOM_SEED


def generate(n=50000):
    random.seed(RANDOM_SEED); np.random.seed(RANDOM_SEED)
    DATA_PATH.parent.mkdir(exist_ok=True)
    users = [f"user_{i:03d}" for i in range(250)]
    receivers = [f"merchant{i:03d}@upi" for i in range(550)]
    profiles = {u: {"mean": np.random.uniform(120, 1800), "hour": np.random.choice(range(8, 22)), "device": f"dev_{u}", "favorites": random.sample(receivers, 8)} for u in users}
    start = datetime.now().replace(second=0, microsecond=0) - timedelta(days=60)
    rows, sender_times = [], {u: [] for u in users}
    for i in range(n):
        u = random.choice(users); p = profiles[u]
        ts = start + timedelta(seconds=int(i * 103 + np.random.exponential(900)))
        # stable habits normally; injected patterns provide learnable fraud signatures
        fraud = random.random() < .025; kind = "genuine"
        receiver = random.choice(p["favorites"]); device = p["device"]
        hour = int(np.clip(np.random.normal(p["hour"], 2.4), 0, 23))
        ts = ts.replace(hour=hour, minute=random.randrange(60))
        amount = max(10, np.random.lognormal(np.log(p["mean"]), .45))
        if fraud:
            kind = random.choice(["takeover", "social", "burst", "malicious_qr"])
            if kind == "takeover": device = f"unknown_{random.randrange(800)}"; receiver = random.choice(receivers); ts = ts.replace(hour=random.choice([1,2,3,4])); amount = p["mean"] * random.uniform(5, 13)
            elif kind == "social": receiver = random.choice(receivers); amount = p["mean"] * random.uniform(4, 10)
            elif kind == "burst":
                receiver = random.choice(receivers); amount = p["mean"] * random.uniform(2, 7); ts = (sender_times[u][-1] + timedelta(seconds=random.randrange(15,180))) if sender_times[u] else ts
            else: receiver = f"quickpay{random.randrange(30)}@suspicious"; amount = p["mean"] * random.uniform(2, 8)
        sender_times[u].append(ts)
        rows.append({"txn_id": str(uuid.uuid4()), "sender_id":u, "receiver_id":receiver, "amount":round(amount,2), "timestamp":ts.isoformat(sep=" "), "hour":ts.hour, "device_id":device, "location":"Bengaluru", "is_new_receiver":int(receiver not in p["favorites"]), "is_fraud":int(fraud), "pattern":kind})
    df = pd.DataFrame(rows).sort_values("timestamp")
    df.to_csv(DATA_PATH, index=False)
    print(f"Wrote {len(df):,} synthetic transactions; fraud rate: {df.is_fraud.mean():.2%}")

if __name__ == "__main__": generate()
