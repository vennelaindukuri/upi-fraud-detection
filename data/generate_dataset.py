"""
Synthetic UPI transaction dataset generator (fully fictional users / receivers).
Outputs: users.csv, receivers.csv, transactions.csv, payee_recommendations.csv
Run:  python generate_dataset.py
"""
import bisect, math, random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED); random.seed(SEED)
H = "@okshield"
START = datetime(2026, 7, 1)
DAYS = 92
N_USERS = 200
FRAUD_RATE = 0.025

# ------------------------------------------------------------------ names
FIRST = ["aarav","aditi","akash","ananya","anil","arjun","bhavya","chaitanya","deepak","divya","farhan","gayatri",
 "harsha","isha","jayant","kavya","kiran","lakshmi","madhav","manasa","meena","naveen","neha","nikhil","pooja",
 "pranav","priya","rahul","rajesh","ramya","ravi","rohit","sai","sandeep","sanjana","shreya","sneha","srinivas",
 "suresh","swathi","tarun","uday","varun","vikram","vinay","yamini","yash","zoya","charan","harini","keerthi",
 "lokesh","mahesh","nandini","padma","rakesh","sahithi","teja","vamsi","anusha","bharath","dinesh","geetha"]
used = set()
def uid(base):
    i = base
    while f"{i}.demo{H}" in used:
        i = f"{base}{random.randint(10,99)}"
    used.add(f"{i}.demo{H}")
    return f"{i}.demo{H}"

# ------------------------------------------------------------------ receivers
rec = []   # dicts
def add_rec(rid, name, rtype, cat, base, age, risk):
    rec.append(dict(receiver_id=rid, receiver_name=name, receiver_type=rtype, category=cat,
                    base_amount=base, account_age_days=int(age), receiver_risk_score=round(float(risk), 3)))

CATS = [("Chai Wala","tea stall",40),("Campus Canteen","canteen",120),("Fresh Mart","grocery",700),
 ("City Pharmacy","pharmacy",450),("Fuel Point","fuel",1500),("Metro Recharge","recharge",300),
 ("Spice Garden","restaurant",600),("Daily Bakery","bakery",250),("Paper Plus","stationery",200),
 ("Style Salon","salon",500),("Quick Ride","cab",180),("Book Nook","books",450),
 ("Gadget Hub","electronics",3000),("Trend Wear","clothing",1500),("Milk Basket","dairy",90),
 ("Veggie Cart","vegetables",150),("Fit Zone","gym",1200),("Clean Wash","laundry",300)]
named = {"Chai Wala":"chaiwala","Campus Canteen":"campuscanteen","Fresh Mart":"freshmart",
         "City Pharmacy":"citypharmacy","Fuel Point":"fuelpoint","Metro Recharge":"metrorecharge"}
for nm, cat, base in CATS:
    if nm in named:
        rid = f"{named[nm]}.demo{H}"; used.add(rid)
        add_rec(rid, nm, "merchant", cat, base, rng.integers(300, 2000), rng.uniform(0, 0.03))
for i in range(250):
    nm, cat, base = CATS[i % len(CATS)]
    rid = uid(nm.lower().replace(" ", "") + str(i // len(CATS) + 1))
    add_rec(rid, f"{nm} {i // len(CATS) + 1}", "merchant", cat, base, rng.integers(150, 2500), rng.uniform(0, 0.03))
used.add(f"cbit-fees.demo{H}")
add_rec(f"cbit-fees.demo{H}", "CBIT Fees Portal", "merchant", "college fees", 18000, 1500, 0.0)
for nm in ["anil", "sneha"]:
    rid = f"{nm}.demo{H}"; used.add(rid)
    add_rec(rid, nm.title(), "peer", "person", 0, rng.integers(200, 3000), rng.uniform(0, 0.02))
for i in range(150):
    nm = random.choice(FIRST)
    add_rec(uid(nm + "p"), nm.title(), "peer", "person", 0, rng.integers(100, 3000), rng.uniform(0, 0.02))
SUS = [("refund-support","Refund Support"),("lucky-draw99","Lucky Draw"),("kyc-update","KYC Update"),("cashback-offer","Cashback Offer")]
for s, nm in SUS:
    rid = f"{s}.demo{H}"; used.add(rid)
    add_rec(rid, nm, "suspicious", "flagged", 0, rng.integers(1, 30), rng.uniform(0.6, 0.95))
for i in range(16):
    s, nm = SUS[i % 4]
    add_rec(uid(f"{s.split('-')[0]}{i+10}"), f"{nm} {i+10}", "suspicious", "flagged", 0, rng.integers(1, 30), rng.uniform(0.55, 0.95))
used.add(f"gift-voucher77.demo{H}")
add_rec(f"gift-voucher77.demo{H}", "Gift Voucher 77", "mule", "new account", 0, 4, 0.2)
for i in range(40):
    add_rec(uid(f"agent{i+1}"), f"Agent {i+1}", "mule", "new account", 0, rng.integers(1, 20), rng.uniform(0.08, 0.35))
# add realism: a few legitimate receivers are brand new accounts, and a few carry false flags
for r_ in rec:
    if r_["receiver_type"] in ("merchant", "peer") and r_["receiver_id"] not in (f"cbit-fees.demo{H}",):
        x = rng.random()
        if x < 0.07:
            r_["account_age_days"] = int(rng.integers(1, 40)); r_["receiver_risk_score"] = round(float(rng.uniform(0.03, 0.3)), 3)
        elif x < 0.10:
            r_["receiver_risk_score"] = round(float(rng.uniform(0.3, 0.55)), 3)
    elif r_["receiver_type"] == "mule" and rng.random() < 0.35:
        r_["receiver_risk_score"] = round(float(rng.uniform(0.0, 0.06)), 3)
        r_["account_age_days"] = int(rng.integers(10, 120))
    elif r_["receiver_type"] == "suspicious" and rng.random() < 0.3:
        r_["receiver_risk_score"] = round(float(rng.uniform(0.3, 0.6)), 3)
R = pd.DataFrame(rec).set_index("receiver_id", drop=False)
merchants = list(R[R.receiver_type == "merchant"].index)
peers = list(R[R.receiver_type == "peer"].index)
sus = list(R[R.receiver_type == "suspicious"].index)
mules = list(R[R.receiver_type == "mule"].index)

# ------------------------------------------------------------------ users
CORE = [("vennela","Vennela","Student",300),("shraddha","Shraddha","Student",350),("ravi","Ravi","Student",250),
        ("priya","Priya","Shopkeeper",3000),("arjun","Arjun","IT employee",1200),("meena","Meena","Homemaker",600),
        ("sai","Sai","Freelancer",1500)]
ROLES = ["Student","Employee","Shopkeeper","Homemaker","Freelancer","Retired","Teacher","Delivery partner"]
users = []
for s, nm, role, avg in CORE:
    i = f"{s}.demo{H}"; used.add(i)
    users.append(dict(user_id=i, name=nm, role=role, typical_amount=avg))
for _ in range(N_USERS - len(CORE)):
    nm = random.choice(FIRST)
    users.append(dict(user_id=uid(nm), name=nm.title(), role=random.choice(ROLES),
                      typical_amount=int(np.clip(rng.lognormal(math.log(600), 0.8), 100, 6000) // 10 * 10)))
for u in users:
    u["rate_per_day"] = round(float(rng.uniform(1.5, 3.5)), 2)
    u["active_start"] = int(rng.integers(8, 12)); u["active_end"] = int(rng.integers(19, 23))
    slug = u["user_id"].split(".")[0]
    u["primary_device"] = f"dev_{slug}_1"
    u["secondary_device"] = f"dev_{slug}_2" if rng.random() < 0.15 else ""
U = pd.DataFrame(users).set_index("user_id", drop=False)

MUST = {"ravi.demo"+H: ["chaiwala.demo"+H, "campuscanteen.demo"+H],
        "vennela.demo"+H: ["campuscanteen.demo"+H, "chaiwala.demo"+H, "metrorecharge.demo"+H, "anil.demo"+H, "sneha.demo"+H],
        "priya.demo"+H: ["freshmart.demo"+H, "fuelpoint.demo"+H], "arjun.demo"+H: ["fuelpoint.demo"+H, "metrorecharge.demo"+H]}

# favourites + typical amount per (user, receiver)
fav = {}
for u in users:
    k = int(rng.integers(6, 13)); favs = list(MUST.get(u["user_id"], []))
    while len(favs) < k:
        r = random.choice(merchants if random.random() < 0.6 else peers)
        if r not in favs and r != f"cbit-fees.demo{H}": favs.append(r)
    w = np.array([1 / (i + 1) for i in range(len(favs))]); w /= w.sum()
    fav[u["user_id"]] = (favs, w)
def typical_for(user_avg, r):
    base = R.at[r, "base_amount"]
    if base > 0:
        return float(np.clip(base * (user_avg / 600) ** 0.6 * rng.lognormal(0, 0.25), 20, 8 * user_avg))
    return float(user_avg * rng.lognormal(0, 0.5))
typ_amt = {(u["user_id"], r): typical_for(u["typical_amount"], r) for u in users for r in fav[u["user_id"]][0]}

# Vennela's habit from the project brief: everyday payments of roughly Rs. 200-400
for (uid_, r), v in list(typ_amt.items()):
    if uid_.startswith("vennela."):
        typ_amt[(uid_, r)] = float(random.choice([200, 250, 300, 350, 400]))

def rnd_amt(x):
    x = max(x, 10)
    step = 5 if x < 100 else 10 if x < 1000 else 50 if x < 10000 else 500 if x < 50000 else 1000
    return int(round(x / step) * step)

# ------------------------------------------------------------------ build transactions
T = []
def add(sender, ts, receiver, amount, device, kind="normal", ftype="none", qr=0, mismatch=0):
    T.append(dict(sender_id=sender, timestamp=ts, receiver_id=receiver, amount=int(amount), device_id=device,
                  is_qr_payment=qr, qr_mismatch=mismatch, txn_kind=kind, fraud_type=ftype,
                  is_fraud=int(kind == "fraud")))

def day_hour(u):
    mid = (u["active_start"] + u["active_end"]) / 2
    h = rng.normal(mid, 3)
    return int(np.clip(h, u["active_start"], u["active_end"] - 1))
def rand_ts(day, hour):
    return START + timedelta(days=int(day), hours=int(hour), minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))
def usual_dev(u):
    return u["secondary_device"] if u["secondary_device"] and rng.random() < 0.1 else u["primary_device"]
new_dev = lambda: f"dev_new_{rng.integers(10000, 99999)}"

for u in users:
    favs, w = fav[u["user_id"]]
    for d in range(DAYS):
        n = rng.poisson(u["rate_per_day"] * (1.25 if (START + timedelta(days=d)).weekday() >= 5 else 1.0))
        for _ in range(n):
            hour = int(rng.integers(0, 24)) if rng.random() < 0.02 else day_hour(u)
            ts = rand_ts(d, hour); dev = usual_dev(u)
            if rng.random() < 0.06:               # genuine new receiver
                r = random.choice(merchants); amt = rnd_amt(typical_for(u["typical_amount"], r) * rng.lognormal(0, 0.15))
            else:
                r = favs[rng.choice(len(favs), p=w)]; amt = rnd_amt(typ_amt[(u["user_id"], r)] * rng.lognormal(0, 0.15))
            kind = "normal"
            if rng.random() < 0.012:              # genuine but unusual
                kind = "legit_unusual"; t = random.choice(["big_purchase", "phone_change", "late_night", "rent_fee", "travel", "young_receiver"])
                if t == "big_purchase": r = random.choice(merchants); amt = rnd_amt(u["typical_amount"] * rng.uniform(3, 8))
                elif t == "phone_change": dev = new_dev()
                elif t == "late_night": ts = rand_ts(d, int(rng.integers(0, 5)))
                elif t == "travel": dev = new_dev(); ts = rand_ts(d, int(rng.integers(0, 24))); amt = rnd_amt(u["typical_amount"] * rng.uniform(2, 5))
                elif t == "young_receiver":
                    young = [m_ for m_ in merchants + peers if R.at[m_, "account_age_days"] < 40]
                    r = random.choice(young); amt = rnd_amt(u["typical_amount"] * rng.uniform(1, 4))
                else: r = random.choice(peers); amt = rnd_amt(u["typical_amount"] * rng.uniform(5, 12))
            qr = int(rng.random() < (0.45 if R.at[r, "receiver_type"] == "merchant" else 0.1))
            add(u["user_id"], ts, r, amt, dev, kind, "none", qr, 0)
# genuine LARGE payments (v2): rent / family transfers to a known person every month, and
# occasional big purchases (Rs.10k-1L) at established, low-risk shops - daytime, usual phone.
# These teach the model that a big amount alone is not fraud; the context around it decides.
established = [m for m in merchants if R.at[m, "account_age_days"] >= 180 and R.at[m, "receiver_risk_score"] < 0.05
               and R.at[m, "category"] in ("electronics", "clothing", "fuel", "gym", "grocery", "restaurant", "pharmacy", "books")]
for u in users:
    favs, _ = fav[u["user_id"]]
    if rng.random() < 0.45:                               # monthly rent / family transfer
        peer_favs = [r for r in favs if R.at[r, "receiver_type"] == "peer" and R.at[r, "account_age_days"] >= 180] or \
                    [p_ for p_ in peers if R.at[p_, "account_age_days"] >= 180][:1]
        rp = random.choice(peer_favs); base = float(rng.uniform(8000, 60000))
        for d in range(int(rng.integers(0, 10)), DAYS, 30):
            add(u["user_id"], rand_ts(d, day_hour(u)), rp, rnd_amt(base * rng.uniform(0.95, 1.05)), u["primary_device"], "legit_large", "none", 0, 0)
    for _ in range(int(rng.poisson(1.6))):                 # one-off big purchase
        d = int(rng.integers(0, DAYS)); r = random.choice(established)
        add(u["user_id"], rand_ts(d, day_hour(u)), r, rnd_amt(rng.uniform(10000, 100000)), usual_dev(u), "legit_large", "none", int(rng.random() < 0.3), 0)
n_gen = len(T)

# fraud events
target = int(FRAUD_RATE * n_gen / (1 - FRAUD_RATE)); n_f = 0
ftypes = ["account_takeover", "amount_spike", "social_engineering", "burst", "malicious_qr"]
fw = [0.25, 0.20, 0.25, 0.15, 0.15]
def fadd(u, ts, r, amt, dev, ft, qr=0, mm=0):
    global n_f
    add(u["user_id"], ts, r, min(rnd_amt(amt), 500000), dev, "fraud", ft, qr, mm); n_f += 1
def fraud_recv(pool_mule=0.55, pool_sus=0.25):
    x = rng.random()
    return random.choice(mules) if x < pool_mule else random.choice(sus) if x < pool_mule + pool_sus else random.choice(merchants + peers)
young_accts = [m_ for m_ in merchants + peers if R.at[m_, "account_age_days"] < 40]
while n_f < target:
    u = users[rng.integers(len(users))]; avg = u["typical_amount"]; d = int(rng.integers(15, DAYS))
    ft = ftypes[rng.choice(5, p=fw)]
    if ft == "account_takeover":
        h = int(rng.integers(0, 6)) if rng.random() < 0.7 else int(rng.integers(22, 24))
        ts = rand_ts(d, h); r = fraud_recv(); dv = new_dev()
        for j in range(int(rng.integers(1, 3))):
            fadd(u, ts + timedelta(minutes=int(rng.integers(1, 10)) * j), r, avg * rng.uniform(8, 60), dv, ft)
    elif ft == "amount_spike":                         # v2: stolen money always lands in an account the fraudster controls
        ts = rand_ts(d, day_hour(u)); x = rng.random()
        r = random.choice(mules) if x < 0.6 else (random.choice(sus) if x < 0.85 else random.choice(young_accts))
        fadd(u, ts, r, avg * rng.uniform(15, 600), usual_dev(u), ft)
    elif ft == "social_engineering":
        ts = rand_ts(d, day_hour(u)); r = fraud_recv(0.45, 0.30)
        for j in range(int(rng.integers(1, 3))):
            fadd(u, ts + timedelta(minutes=int(rng.integers(2, 15)) * j), r, avg * rng.uniform(1.5, 15), usual_dev(u), ft)
    elif ft == "burst":
        ts = rand_ts(d, int(rng.integers(0, 24))); r = fraud_recv(0.5, 0.3)
        dv = new_dev() if rng.random() < 0.4 else usual_dev(u)
        for j in range(int(rng.integers(4, 9))):
            ts += timedelta(seconds=int(rng.integers(15, 120)))
            fadd(u, ts, r, avg * rng.uniform(0.5, 3), dv, ft)
    else:
        ts = rand_ts(d, day_hour(u)); r = fraud_recv(0.4, 0.4)
        fadd(u, ts, r, avg * rng.uniform(0.8, 5), usual_dev(u), ft, 1, 1)

# hand-written Vennela story (as in the project brief): small payments, then sudden lakhs
V = users[0]; assert V["user_id"].startswith("vennela")
add(V["user_id"], datetime(2026, 8, 20, 11, 20, 14), f"cbit-fees.demo{H}", 18000, V["primary_device"], "legit_unusual", "none", 1, 0)
fadd(V, datetime(2026, 9, 5, 15, 42, 31), f"gift-voucher77.demo{H}", 200000, V["primary_device"], "amount_spike")
fadd(V, datetime(2026, 9, 12, 2, 47, 9), f"lucky-draw99.demo{H}", 150000, "dev_new_90001", "account_takeover")
fadd(V, datetime(2026, 9, 20, 13, 5, 48), f"refund-support.demo{H}", 2500, V["primary_device"], "social_engineering")

# ------------------------------------------------------------------ behavioural features (past data only)
df = pd.DataFrame(T).sort_values(["sender_id", "timestamp"]).reset_index(drop=True)
out = []
for sid, g in df.groupby("sender_id", sort=False):
    u = U.loc[sid]; seen_dev = {u["primary_device"]} | ({u["secondary_device"]} if u["secondary_device"] else set())
    past_ts, past_amt, paid = [], [], {}
    rs = 0.0; rs2 = 0.0; mx = 0.0
    for row in g.itertuples(index=False):
        n = len(past_amt); t = row.timestamp.timestamp()
        c1 = n - bisect.bisect_left(past_ts, t - 3600); c24 = n - bisect.bisect_left(past_ts, t - 86400)
        if n >= 5:
            mean = rs / n; std = math.sqrt(max(rs2 / n - mean ** 2, 0)); mxa = mx
        else:
            mean = u["typical_amount"]; std = 0.5 * mean; mxa = mean
        z = (row.amount - mean) / max(std, 0.3 * mean)
        out.append(dict(txn_count_1h=c1, txn_count_24h=c24, avg_amount_hist=round(mean, 2), amount_zscore=round(z, 3),
                        amount_ratio=round(row.amount / mean, 3), amount_vs_max=round(row.amount / max(mxa, 1), 3),
                        is_new_receiver=int(row.receiver_id not in paid), receiver_pay_count=paid.get(row.receiver_id, 0),
                        time_since_last_min=round((t - past_ts[-1]) / 60, 2) if n else 9999.0,
                        is_new_device=int(row.device_id not in seen_dev)))
        seen_dev.add(row.device_id); past_ts.append(t); past_amt.append(row.amount)
        rs += row.amount; rs2 += row.amount ** 2; mx = max(mx, row.amount)
        paid[row.receiver_id] = paid.get(row.receiver_id, 0) + 1
df = pd.concat([df, pd.DataFrame(out)], axis=1)
df = df.sort_values("timestamp").reset_index(drop=True)
df.insert(0, "txn_id", [f"T{i+1:06d}" for i in range(len(df))])
df["hour"] = df.timestamp.dt.hour; df["day_of_week"] = df.timestamp.dt.dayofweek
df["is_weekend"] = (df.day_of_week >= 5).astype(int); df["is_odd_hour"] = (df.hour < 6).astype(int)
for c in ["receiver_type", "receiver_name", "receiver_risk_score", "account_age_days"]:
    df[c] = df.receiver_id.map(R[c])
df = df.rename(columns={"account_age_days": "receiver_account_age_days"})
cols = ["txn_id","timestamp","sender_id","receiver_id","receiver_name","receiver_type","amount","device_id","hour","day_of_week",
 "is_weekend","is_odd_hour","is_qr_payment","qr_mismatch","txn_count_1h","txn_count_24h","time_since_last_min",
 "avg_amount_hist","amount_zscore","amount_ratio","amount_vs_max","is_new_receiver","receiver_pay_count","is_new_device",
 "receiver_risk_score","receiver_account_age_days","txn_kind","fraud_type","is_fraud"]
df = df[cols]; df["timestamp"] = df.timestamp.dt.strftime("%Y-%m-%d %H:%M:%S")

# ------------------------------------------------------------------ payee recommendations (non-fraud history)
g = df[(df.is_fraud == 0) & df.receiver_type.isin(["merchant", "peer"])].copy()
g["ts"] = pd.to_datetime(g.timestamp); end = g.ts.max()
agg = g.groupby(["sender_id", "receiver_id"]).agg(times_paid=("amount", "size"), avg_amount=("amount", "mean"), last_paid=("ts", "max")).reset_index()
agg["days_since_last"] = (end - agg.last_paid).dt.total_seconds() / 86400
agg["freq_norm"] = agg.groupby("sender_id").times_paid.transform(lambda s: s / s.max())
agg["recency"] = np.exp(-agg.days_since_last / 14)
agg["score"] = (0.6 * agg.freq_norm + 0.4 * agg.recency).round(4)
agg["rank"] = agg.groupby("sender_id").score.rank(ascending=False, method="first").astype(int)
rec_df = agg[agg["rank"] <= 5].sort_values(["sender_id", "rank"]).copy()
rec_df["receiver_name"] = rec_df.receiver_id.map(R.receiver_name); rec_df["receiver_type"] = rec_df.receiver_id.map(R.receiver_type)
rec_df["avg_amount"] = rec_df.avg_amount.round(0).astype(int); rec_df["last_paid"] = rec_df.last_paid.dt.strftime("%Y-%m-%d")
rec_df = rec_df[["sender_id","rank","receiver_id","receiver_name","receiver_type","times_paid","avg_amount","last_paid","score"]]

# ------------------------------------------------------------------ write
U[["user_id","name","role","typical_amount","rate_per_day","active_start","active_end","primary_device","secondary_device"]].to_csv("users.csv", index=False)
R.drop(columns=["base_amount"]).to_csv("receivers.csv", index=False)
df.to_csv("transactions.csv", index=False)
rec_df.to_csv("payee_recommendations.csv", index=False)
print("users", len(U), "receivers", len(R), "txns", len(df), "fraud", int(df.is_fraud.sum()), f"({df.is_fraud.mean():.2%})")
print(df.fraud_type.value_counts().to_string()); print(df.txn_kind.value_counts().to_string())
