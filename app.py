import csv, time, uuid, secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import cv2, joblib, numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from config import MODEL_DIR, REPORT_DIR, FEATURE_COLUMNS, RF_WEIGHT, ANOMALY_WEIGHT, ALLOW_THRESHOLD, BLOCK_THRESHOLD, OTP_TTL_SECONDS, OTP_MAX_ATTEMPTS
from db import init_db, connect, recent_history, insert_transaction
from dataset_features import live_features, ae_input, blend

app = Flask(__name__)
pending = {}
VELOCITY_LIMIT = 3
DAILY_LIMIT = 100000   # Rs. per sender per day, like the NPCI UPI cap
_model_bundle = None


def bundle():
    """Load once at process startup/use, never in the payment hot path."""
    global _model_bundle
    if _model_bundle is None:
        _model_bundle = joblib.load(MODEL_DIR / "fraud_model.joblib")
    return _model_bundle


FEATURE_LABELS = {
    "amount": "Amount", "hour": "Time of day", "is_odd_hour": "Night-time (before 5 AM)", "is_qr_payment": "Paid by QR",
    "qr_mismatch": "QR name mismatch", "txn_count_1h": "Payments in last hour", "txn_count_24h": "Payments in last 24 h",
    "time_since_last_min": "Time since last payment", "amount_zscore": "Amount vs usual spread", "amount_ratio": "Amount vs average",
    "amount_vs_max": "Amount vs largest ever", "is_new_receiver": "New receiver", "receiver_pay_count": "Times paid this receiver",
    "is_new_device": "Unrecognised device", "receiver_risk_score": "Receiver risk score", "receiver_account_age_days": "Receiver account age"}
_baseline = None


def baseline():
    """A 'typical genuine payment' vector: medians of genuine transactions in the dataset."""
    global _baseline
    if _baseline is None:
        with connect() as con:
            df = pd.read_sql(f"SELECT {','.join(FEATURE_COLUMNS)} FROM dataset_transactions WHERE is_fraud=0", con)
        _baseline = {c: float(df[c].median()) for c in FEATURE_COLUMNS}
    return _baseline


def blended(b, X):
    rf = b["model"].predict_proba(X)[:, 1]
    Z = b["scaler"].transform(ae_input(X) if b.get("ae_log") else X)
    err = np.mean((b["autoencoder"].predict(Z) - Z) ** 2, axis=1)
    an = np.clip((err - b["anom_lo"]) / (b["anom_hi"] - b["anom_lo"] + 1e-9), 0, 1)
    return rf, an, blend(rf, an, RF_WEIGHT, ANOMALY_WEIGHT)


def explain(x):
    """Per-feature contribution: how much the blended risk drops when that one feature is reset
    to a typical genuine value (occlusion). Positive = pushed risk up."""
    b, base = bundle(), baseline()
    rows = [x.iloc[0].copy()]
    for c in FEATURE_COLUMNS:
        r = x.iloc[0].copy(); r[c] = base[c]; rows.append(r)
    X = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    risk = blended(b, X)[2]
    out = [{"feature": c, "label": FEATURE_LABELS.get(c, c), "value": round(float(x.iloc[0][c]), 2), "typical": round(base[c], 2),
            "impact": round(float(risk[0] - risk[i + 1]), 4)} for i, c in enumerate(FEATURE_COLUMNS)]
    out = [o for o in out if abs(o["impact"]) >= 0.005]
    return sorted(out, key=lambda o: -abs(o["impact"]))[:6]


def init_attempts():
    """Every scored payment attempt (allowed, challenged or blocked) is logged here.
    Attempts feed the velocity features, so a burst of rapid payments escalates even
    when the earlier ones were never completed."""
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS attempts (
          token TEXT PRIMARY KEY, sender_id TEXT, receiver_id TEXT, amount REAL,
          created_at REAL, demo_time TEXT, decision TEXT, risk_score REAL,
          latency_ms REAL, confirmed INTEGER DEFAULT 0, reasons TEXT)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_attempt_sender ON attempts(sender_id, created_at)")


def recent_attempts(sender, now_real, exclude=None):
    """Unconfirmed attempts by this sender (confirmed ones are already in the transaction history)."""
    with connect() as con:
        rows = con.execute("SELECT created_at FROM attempts WHERE sender_id=? AND confirmed=0 AND created_at>=? AND token IS NOT ?",
                           (sender, now_real - 86400, exclude)).fetchall()
    ts = [r["created_at"] for r in rows]
    return (sum(t >= now_real - 3600 for t in ts), len(ts), max(ts) if ts else None)


def reasons(f, decision):
    pairs = []
    if f.get("takeover_guard"): pairs.append((18, "New phone, at night, far above your usual amount — looks like account takeover"))
    if f.get("pair_guard") == 2:
        pairs.append((16, f"Far above anything you've paid this receiver (largest so far ₹{inr(f['pair_max'])})" if f.get("pair_max") else "Large first payment to a new or unverified account"))
    if f.get("pair_guard") == 1:
        pairs.append((17, f"More than you've paid this receiver before (largest ₹{inr(f['pair_max'])}) — confirm it's you" if f.get("pair_max") else "Large first payment to this receiver — confirm it's you"))
    if f.get("qr_stepup"): pairs.append((19, "QR looked tampered — extra verification required"))
    if f.get("velocity_guard"): pairs.append((20, f"Velocity guard: {int(f['txn_count_1h'])} rapid attempts — burst pattern"))
    if f["qr_mismatch"]: pairs.append((9, "QR name doesn't match the registered UPI ID"))
    if f["receiver_risk_score"] > .3: pairs.append((8, "Receiver is on the risk watch-list"))
    elif f["receiver_risk_score"] > .05: pairs.append((4, "Receiver has prior flagged activity"))
    if f["txn_count_1h"] >= 3 and not f.get("velocity_guard"): pairs.append((f["txn_count_1h"] + 2, f"{int(f['txn_count_1h'])} payment attempts in the last hour"))
    if f["amount_ratio"] >= 3: pairs.append((min(f["amount_ratio"], 50) / 3 + 3, f"Amount is {f['amount_ratio']:.1f}× your usual payment"))
    if f["is_new_device"]: pairs.append((5, "Payment from a device we haven't seen"))
    if f["is_odd_hour"]: pairs.append((3, "Unusual late-night payment time"))
    if f["receiver_account_age_days"] < 30: pairs.append((3, f"Receiver account is only {int(f['receiver_account_age_days'])} days old"))
    if f["is_new_receiver"]: pairs.append((2.5, "First payment to this receiver"))
    out = [x[1] for x in sorted(pairs, reverse=True)[:3]]
    if out: return out
    return ["Matches your usual payment pattern"] if decision == "ALLOW" else ["Combined behavioural risk is elevated"]


def score(sender, receiver, amount, device, demo_hour=None, is_qr=0, qr_mismatch=0, exclude=None):
    real = datetime.now()
    now = real.replace(microsecond=0)
    if demo_hour is not None:
        now = now.replace(hour=int(demo_hour))
    history = recent_history(sender, now, hours=24*365)
    with connect() as con:
        user = con.execute("SELECT * FROM users WHERE upi_id=?", (sender,)).fetchone()
        receiver_info = con.execute("SELECT * FROM receivers WHERE upi_id=?", (receiver,)).fetchone()
    if not user: raise ValueError("Unknown fictional demo sender")
    feat = live_features(sender, receiver, amount, device, now, history, user, receiver_info, is_qr, qr_mismatch)
    # Velocity also counts attempts that were challenged or blocked.
    n1h, n24, last = recent_attempts(sender, real.timestamp(), exclude)
    feat["txn_count_1h"] += n1h
    feat["txn_count_24h"] += n24
    if last is not None:
        feat["time_since_last_min"] = min(feat["time_since_last_min"], (real.timestamp() - last) / 60)
    b = bundle()
    x = pd.DataFrame([[feat[c] for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)
    rf, anomaly, model_risk = (float(v[0]) for v in blended(b, x))
    # Receiver floor: a watch-listed receiver can never score below 30% of its risk score.
    # Disclosed in the response (floor_applied) so the UI can show when it overrode the model.
    floor = feat["receiver_risk_score"] * .30
    risk = min(1.0, max(model_risk, floor))
    feat["floor_applied"] = int(floor > model_risk)
    decision = "ALLOW" if risk < ALLOW_THRESHOLD else "OTP VERIFY" if risk <= BLOCK_THRESHOLD else "BLOCK"
    # QR step-up: a QR whose name doesn't match the registered payee is never waved through.
    feat["qr_stepup"] = int(bool(qr_mismatch) and decision == "ALLOW")
    if feat["qr_stepup"]:
        decision, risk = "OTP VERIFY", max(risk, ALLOW_THRESHOLD)
    # Takeover guard: unknown phone + night (before 6 AM) + far above the sender's usual amount = classic
    # account-takeover signature -> block, whatever the receiver looks like.
    feat["takeover_guard"] = int(feat["is_new_device"] == 1 and now.hour < 6 and feat["amount_ratio"] >= 5)
    if feat["takeover_guard"] and decision != "BLOCK":
        decision, risk = "BLOCK", max(risk, BLOCK_THRESHOLD + 0.01)
    # Pair guard: a big payment is only normal if this sender has paid THIS receiver similar amounts before.
    # e.g. paid Anil up to Rs.35,500 -> Rs.50,000 is fine; Chai Wala max Rs.420 -> Rs.50,000 is put on hold.
    with connect() as con:
        pm = con.execute("SELECT coalesce(max(amount),0) FROM transactions WHERE sender_id=? AND receiver_id=? AND is_fraud=0",
                         (sender, receiver)).fetchone()[0]
    feat["pair_max"] = float(pm)
    typical = float(user["typical_amount"] or 0)
    established_rcv = bool(receiver_info) and (receiver_info["account_age_days"] or 0) >= 180 and not receiver_info["is_flagged"]
    feat["pair_guard"] = 0
    if amount >= max(10000, 5 * typical) and pm < amount * 0.5:
        if (pm > 0 and amount <= 5 * pm) or (pm == 0 and established_rcv):
            feat["pair_guard"] = 1          # somewhat above the usual for this receiver -> OTP
            if decision == "ALLOW": decision, risk = "OTP VERIFY", max(risk, ALLOW_THRESHOLD + 0.05)
        else:
            feat["pair_guard"] = 2          # far above anything paid to this receiver -> on hold
            if decision != "BLOCK": decision, risk = "BLOCK", max(risk, BLOCK_THRESHOLD + 0.05)
    # Velocity guard: a rule layer on top of the model. 3+ unfinished attempts within the
    # hour that the model already finds risky are treated as a burst attack and blocked.
    feat["velocity_guard"] = int(n1h >= VELOCITY_LIMIT and decision != "ALLOW")
    if feat["velocity_guard"]:
        decision, risk = "BLOCK", max(risk, BLOCK_THRESHOLD + 0.01)
    return dict(now=now, feat=feat, risk=risk, decision=decision, rf=rf, anomaly=anomaly, model_risk=model_risk, x=x)


@app.get("/")
def landing(): return render_template("landing.html")


@app.get("/app")
def index(): return render_template("index.html")


@app.get("/demo-qr")
def demo_qr():
    with connect() as con:
        rows = [dict(r) for r in con.execute("SELECT upi_id,name,category FROM receivers WHERE upi_id NOT GLOB '*[0-9]*.demo@okshield' OR category IN ('suspicious','mule') ORDER BY CASE category WHEN 'merchant' THEN 0 WHEN 'peer' THEN 1 ELSE 2 END, name")]
    static_qr = Path(app.static_folder) / "qr"
    qrs = [{"file": r["upi_id"].split("@")[0] + ".png", **r} for r in rows]
    qrs = [q for q in qrs if (static_qr / q["file"]).exists()]
    qrs += [{"file": "tampered-name.png", "name": "Tampered: name mismatch", "upi_id": "cashback-offer.demo@okshield", "category": "tampered"},
            {"file": "tampered-malformed.png", "name": "Tampered: malformed payload", "upi_id": "—", "category": "tampered"},
            {"file": "tampered-brand.png", "name": "Tampered: imitation brand", "upi_id": "refund-support.demo@okshield", "category": "tampered"}]
    return render_template("qr_gallery.html", qrs=qrs)


@app.post("/scan_qr")
def scan_qr():
    f = request.files.get("image")
    if not f: return jsonify(error="Upload a QR image."), 400
    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None: return jsonify(error="That file isn't an image."), 400
    data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    if not data: return jsonify(suspicious=True, warning="No QR code could be read from this image", receiver="", name="", amount="", uri="")
    parsed = urlparse(data); q = parse_qs(parsed.query)
    receiver, name = q.get("pa", [""])[0], q.get("pn", [""])[0]
    suspicious = not data.startswith("upi://pay") or not receiver or "@okshield" not in receiver
    warning = "Malformed QR payload" if suspicious else ""
    mismatch = 0
    with connect() as con:
        known = con.execute("SELECT name,is_flagged FROM receivers WHERE upi_id=?", (receiver,)).fetchone()
    if not suspicious and (not known or known["name"].casefold() != name.casefold()):
        suspicious, warning, mismatch = True, "QR name does not match the registered UPI ID", 1
    elif known and known["is_flagged"]:
        suspicious, warning = True, "Receiver is flagged in the risk directory"
    return jsonify(uri=data, receiver=receiver, name=name, amount=q.get("am", [""])[0], suspicious=suspicious,
                   warning=warning, qr_mismatch=mismatch, registered_name=known["name"] if known else None)


def sent_today(sender):
    """Money this sender has already sent today in the demo (completed payments only)."""
    with connect() as con:
        r = con.execute("SELECT coalesce(sum(amount),0) s, count(*) n FROM transactions WHERE sender_id=? AND location='Demo' AND date(timestamp)=date('now','localtime')",
                        (sender,)).fetchone()
    return float(r["s"]), int(r["n"])


def inr(n):
    """Indian digit grouping: 100000 -> 1,00,000."""
    n = int(round(n)); s = str(n)
    if len(s) <= 3: return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
    if head: parts.insert(0, head)
    return ",".join(parts) + "," + tail


def limit_check(sender, amount):
    used, _ = sent_today(sender); left = max(0.0, DAILY_LIMIT - used)
    if amount > left:
        msg = (f"UPI daily limit is ₹{inr(DAILY_LIMIT)} per day. " + (f"You can send up to ₹{inr(left)} more today." if left > 0 else "You've used it all today — try again tomorrow."))
        return {"error": msg, "limit": True, "daily_limit": DAILY_LIMIT, "used_today": used, "left_today": left}
    return None


def score_request(d, exclude=None):
    return score(d["sender_id"], d["receiver_id"].strip(), float(d["amount"]), d["device_id"],
                 d.get("demo_hour"), int(d.get("is_qr", 0)), int(d.get("qr_mismatch", 0)), exclude)


def bad_request(e):
    msg = str(e) if isinstance(e, ValueError) and "Unknown" in str(e) else "sender_id, receiver_id, amount and device_id are required"
    return jsonify(error=msg), 400


@app.get("/pair_stats")
def pair_stats():
    """How much this sender usually sends this receiver, plus today's limit."""
    sender, receiver = request.args.get("sender", ""), request.args.get("receiver", "").strip()
    with connect() as con:
        r = con.execute("""SELECT count(*) n, avg(amount) a, max(amount) mx, sum(amount) total, max(timestamp) last
            FROM transactions WHERE sender_id=? AND receiver_id=? AND is_fraud=0 AND decision='ALLOW'""", (sender, receiver)).fetchone()
        rec = con.execute("SELECT name, category, account_age_days, is_flagged FROM receivers WHERE upi_id=?", (receiver,)).fetchone()
        u = con.execute("SELECT typical_amount FROM users WHERE upi_id=?", (sender,)).fetchone()
    used, _ = sent_today(sender)
    return jsonify(times=r["n"], avg=round(r["a"] or 0), max=round(r["mx"] or 0), total=round(r["total"] or 0), last=r["last"],
                   receiver=dict(rec) if rec else None, typical=u["typical_amount"] if u else None,
                   daily_limit=DAILY_LIMIT, used_today=used, left_today=max(0, DAILY_LIMIT - used))


@app.post("/users")
def add_user():
    """Create a new demo sender. With no history yet, the model starts from a typical amount for their role."""
    import re
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()[:40]; role = (d.get("role") or "Student").strip()[:30]
    if not name: return jsonify(error="Enter a name"), 400
    # no history yet: start from a typical amount for the role; the model learns real habits as they pay
    typical = {"Student": 500, "Employee": 3000, "Shopkeeper": 5000, "Business owner": 10000,
               "Homemaker": 1500, "Freelancer": 3000, "Retired": 2000}.get(role, 2000)
    slug = re.sub(r"[^a-z0-9]", "", name.lower())[:16] or "user"
    with connect() as con:
        base, i = slug, 1
        while con.execute("SELECT 1 FROM users WHERE upi_id=?", (f"{slug}.demo@okshield",)).fetchone():
            i += 1; slug = f"{base}{i}"
        upi = f"{slug}.demo@okshield"
        con.execute("INSERT INTO users (upi_id,name,role,typical_amount,usual_device) VALUES (?,?,?,?,?)", (upi, name, role, typical, f"dev_{slug}_1"))
    return jsonify(upi_id=upi, name=name, role=role, typical_amount=typical, usual_device=f"dev_{slug}_1")


@app.post("/whatif")
def whatif():
    """Score a hypothetical payment without logging it (powers the what-if sliders)."""
    d = request.get_json(force=True)
    try:
        s = score_request(d, exclude=d.get("token"))  # the payment being explored doesn't count against itself
    except (KeyError, ValueError, TypeError) as e:
        return bad_request(e)
    return jsonify(risk_score=round(s["risk"], 3), decision=s["decision"], reasons=reasons(s["feat"], s["decision"])[:2])


@app.get("/profile/<user_id>")
def profile(user_id):
    """Recent genuine spending, for the 'compared to usual' chart."""
    with connect() as con:
        u = con.execute("SELECT * FROM users WHERE upi_id=?", (user_id,)).fetchone()
        if not u: return jsonify(error="Unknown user"), 404
        rows = con.execute("""SELECT t.timestamp, t.amount, t.receiver_id, coalesce(r.name, t.receiver_id) name FROM transactions t
            LEFT JOIN receivers r ON r.upi_id=t.receiver_id WHERE t.sender_id=? AND t.is_fraud=0 AND t.decision='ALLOW'
            ORDER BY t.timestamp DESC LIMIT 30""", (user_id,)).fetchall()
    amts = [r["amount"] for r in rows]
    return jsonify(user=dict(u), recent=[dict(r) for r in rows][::-1],
                   median=float(np.median(amts)) if amts else float(u["typical_amount"]), typical=float(u["typical_amount"]))


@app.get("/activity/<user_id>")
def activity(user_id):
    """Everything this sender tried in the demo plus their latest recorded payments."""
    with connect() as con:
        tried = [dict(r) for r in con.execute("""SELECT a.*, coalesce(r.name, a.receiver_id) name FROM attempts a
            LEFT JOIN receivers r ON r.upi_id=a.receiver_id WHERE a.sender_id=? ORDER BY a.created_at DESC LIMIT 40""", (user_id,))]
        past = [dict(r) for r in con.execute("""SELECT t.txn_id, t.timestamp, t.amount, t.receiver_id, t.is_fraud, t.location, t.device_id,
            coalesce(r.name, t.receiver_id) name, coalesce(r.category, '') category FROM transactions t
            LEFT JOIN receivers r ON r.upi_id=t.receiver_id WHERE t.sender_id=? ORDER BY t.timestamp DESC LIMIT 40""", (user_id,))]
        tot = con.execute("SELECT count(*) n, sum(is_fraud) f, avg(amount) a FROM transactions WHERE sender_id=?", (user_id,)).fetchone()
    return jsonify(attempts=tried, payments=past, totals=dict(tot))


@app.get("/reports/<path:name>")
def reports(name):
    if not name.endswith((".png", ".csv")): abort(404)
    return send_from_directory(REPORT_DIR, name, max_age=0)


@app.post("/predict")
def predict():
    started = time.perf_counter(); d = request.get_json(force=True)
    try:
        # Attack-screen demos skip the daily limit so they always reach the model during a demo
        over = None if d.get("demo") else limit_check(d["sender_id"], float(d["amount"]))
    except (KeyError, ValueError, TypeError) as e:
        return bad_request(e)
    if over: return jsonify(over), 400
    try:
        s = score_request(d)
    except (KeyError, ValueError, TypeError) as e:
        return bad_request(e)
    now, f, risk, decision, rf, anomaly = s["now"], s["feat"], s["risk"], s["decision"], s["rf"], s["anomaly"]
    token = str(uuid.uuid4())
    latency = round((time.perf_counter() - started) * 1000, 1)
    why = reasons(f, decision)
    pending[token] = {"data": d, "time": now, "features": f, "risk": risk, "decision": decision}
    with connect() as con:
        con.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,0,?)",
                    (token, d["sender_id"], d["receiver_id"].strip(), float(d["amount"]), time.time(), now.isoformat(sep=" "),
                     decision, risk, latency, " | ".join(why)))
    result = {"token": token, "risk_score": round(risk, 3), "decision": decision, "reasons": why, "latency_ms": latency,
              "components": {"rf": round(rf, 3), "anomaly": round(anomaly, 3), "model": round(s["model_risk"], 3)},
              "explain": explain(s["x"]),
              "features": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()},
              "thresholds": {"allow": ALLOW_THRESHOLD, "block": BLOCK_THRESHOLD}}
    if decision == "OTP VERIFY":
        otp = f"{secrets.randbelow(1000000):06d}"
        pending[token].update(otp=otp, expires=time.time() + OTP_TTL_SECONDS, attempts=0)
        result["simulated_sms"] = f"Your REDFLAG verification code is {otp}. Valid for 60 seconds. Never share it with anyone."
        result["otp_ttl"] = OTP_TTL_SECONDS
    return jsonify(result)


@app.post("/step_up")
def step_up():
    """Blocked, but the account owner says it is genuine: send a fresh OTP to the registered phone.
    One chance per payment; the code must be entered within 60 s and 3 tries, otherwise it stays blocked.
    A fraudster who only stole the login never receives the code, so the block still protects the account."""
    d = request.get_json(force=True); token = d.get("token"); p = pending.get(token)
    if not p: return jsonify(error="Payment session not found"), 404
    if p["decision"] != "BLOCK": return jsonify(error="Only a blocked payment can be continued this way"), 400
    if p.get("stepped_up"): return jsonify(error="Extra verification was already tried for this payment"), 403
    otp = f"{secrets.randbelow(1000000):06d}"
    p.update(decision="OTP VERIFY", stepped_up=True, otp=otp, expires=time.time() + OTP_TTL_SECONDS, attempts=0)
    with connect() as con:
        con.execute("UPDATE attempts SET reasons = reasons || ' | Owner requested override (OTP sent)' WHERE token=?", (token,))
    return jsonify(ok=True, decision="OTP VERIFY", otp_ttl=OTP_TTL_SECONDS,
                   simulated_sms=f"REDFLAG: a blocked payment of Rs.{float(p['data']['amount']):,.0f} is waiting. If this was you, your code is {otp}. Valid 60 s. If not, ignore this message.")


QR_DEMO = ["chaiwala", "campuscanteen", "freshmart", "citypharmacy", "fuelpoint", "metrorecharge"]


@app.get("/qr_options")
def qr_options():
    """QR codes the payment screen offers to 'scan' (genuine shops first, then tampered ones)."""
    folder = Path(app.static_folder) / "qr"
    with connect() as con:
        names = {r["upi_id"]: r["name"] for r in con.execute("SELECT upi_id,name FROM receivers")}
    out = [{"file": f"{k}.demo.png", "label": names.get(f"{k}.demo@okshield", k), "kind": "shop"} for k in QR_DEMO]
    out += [{"file": "tampered-name.png", "label": "Cashback poster", "kind": "unknown"},
            {"file": "tampered-brand.png", "label": "Refund desk sticker", "kind": "unknown"},
            {"file": "tampered-malformed.png", "label": "Torn sticker", "kind": "unknown"}]
    return jsonify([o for o in out if (folder / o["file"]).exists()])


@app.post("/verify_otp")
def verify_otp():
    d = request.get_json(force=True); p = pending.get(d.get("token"))
    if not p or p["decision"] != "OTP VERIFY": return jsonify(ok=False, decision="BLOCK", message="No valid verification session"), 400
    p["attempts"] += 1
    if time.time() > p["expires"] or p["attempts"] > OTP_MAX_ATTEMPTS:
        p["decision"] = "BLOCK"; _set_attempt(d.get("token"), "BLOCK")
        return jsonify(ok=False, decision="BLOCK", message="Code expired or too many attempts — payment blocked")
    if d.get("otp") != p["otp"]:
        left = OTP_MAX_ATTEMPTS - p["attempts"]
        if left <= 0:
            p["decision"] = "BLOCK"; _set_attempt(d.get("token"), "BLOCK")
            return jsonify(ok=False, decision="BLOCK", message="Too many wrong codes — payment blocked")
        return jsonify(ok=False, decision="OTP VERIFY", attempts_left=left, message=f"Incorrect code · {left} attempt{'s' if left > 1 else ''} left")
    p["decision"] = "ALLOW"; return jsonify(ok=True, decision="ALLOW", message="Code verified")


def _set_attempt(token, decision=None, confirmed=None):
    with connect() as con:
        if decision: con.execute("UPDATE attempts SET decision=? WHERE token=?", (decision, token))
        if confirmed is not None: con.execute("UPDATE attempts SET confirmed=? WHERE token=?", (confirmed, token))


@app.post("/confirm")
def confirm():
    d = request.get_json(force=True); token = d.get("token"); p = pending.get(token)
    if not p: return jsonify(error="Payment session not found"), 404
    if p["decision"] == "OTP VERIFY": return jsonify(error="Verify the code first"), 403
    if p["decision"] == "BLOCK": return jsonify(error="Payment is blocked"), 403
    if p.get("done"): return jsonify(ok=True, message="Payment already completed")
    x = p["data"]
    insert_transaction({"txn_id": str(uuid.uuid4()), "sender_id": x["sender_id"], "receiver_id": x["receiver_id"].strip(), "amount": float(x["amount"]),
                        "timestamp": p["time"].isoformat(sep=" "), "hour": p["time"].hour, "device_id": x["device_id"], "location": "Demo",
                        "is_new_receiver": p["features"]["is_new_receiver"], "is_fraud": 0, "decision": "ALLOW", "risk_score": p["risk"], "latency_ms": 0})
    p["done"] = True; _set_attempt(token, confirmed=1)
    return jsonify(ok=True, message="Payment completed")


@app.get("/history/<user_id>")
def history(user_id):
    with connect() as con: rows = con.execute("SELECT * FROM transactions WHERE sender_id=? ORDER BY timestamp DESC LIMIT 20", (user_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/users")
def users():
    priority = "vennela.demo@okshield,shraddha.demo@okshield,ravi.demo@okshield,priya.demo@okshield,arjun.demo@okshield,meena.demo@okshield,sai.demo@okshield"
    with connect() as con:
        rows = con.execute("SELECT * FROM users WHERE instr(?, upi_id)>0 OR rowid > 200 ORDER BY instr(?, upi_id)=0, instr(?, upi_id), rowid", (priority, priority, priority)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/recommend/<user_id>")
def recommend(user_id):
    """Frequency/recency payees from the live transaction table, never risky ones."""
    import math
    with connect() as con:
        rows = con.execute("""SELECT t.receiver_id,r.name,r.category,count(*) times_paid,avg(t.amount) average_amount,max(t.timestamp) last_paid
          FROM transactions t JOIN receivers r ON r.upi_id=t.receiver_id
          WHERE t.sender_id=? AND r.category NOT IN ('suspicious','mule') AND t.is_fraud=0 AND t.decision!='BLOCK'
          GROUP BY t.receiver_id ORDER BY times_paid DESC,last_paid DESC""", (user_id,)).fetchall()
    now = datetime.now(); max_count = max([r['times_paid'] for r in rows] or [1]); out = []
    for r in rows:
        days = max(0, (now - datetime.fromisoformat(r['last_paid'])).days)
        out.append({**dict(r), 'average_amount': round(r['average_amount']), 'score': round(.6 * (r['times_paid'] / max_count) + .4 * math.exp(-days / 14), 4)})
    return jsonify(sorted(out, key=lambda x: x['score'], reverse=True)[:5])


@app.get("/scenarios")
def scenarios():
    V = "vennela.demo@okshield"; D = "dev_vennela_1"
    return jsonify({
        "normal":   {"title": "Everyday payment", "story": "₹300 at the campus canteen, usual phone, 1 PM", "sender_id": V, "receiver_id": "campuscanteen.demo@okshield", "amount": 300, "device_id": D, "demo_hour": 13},
        "unusual":  {"title": "Genuine but unusual", "story": "₹18,000 college fees — big, but legitimate", "sender_id": V, "receiver_id": "cbit-fees.demo@okshield", "amount": 18000, "device_id": D, "demo_hour": 13},
        "social":   {"title": "Social engineering", "story": "₹2,500 to a 'Refund Support' account", "sender_id": V, "receiver_id": "refund-support.demo@okshield", "amount": 2500, "device_id": D, "demo_hour": 13},
        "spike":    {"title": "Amount spike", "story": "₹95,000 to a brand-new gift-voucher account", "sender_id": V, "receiver_id": "gift-voucher77.demo@okshield", "amount": 95000, "device_id": D, "demo_hour": 15},
        "takeover": {"title": "Account takeover", "story": "₹90,000 from an unknown phone at 2 AM", "sender_id": V, "receiver_id": "lucky-draw99.demo@okshield", "amount": 90000, "device_id": "new-device-demo", "demo_hour": 2},
        "burst":    {"title": "Rapid burst", "story": "Five ₹500 payments to 'KYC Update' in seconds", "sender_id": V, "receiver_id": "kyc-update.demo@okshield", "amount": 500, "device_id": D, "demo_hour": 13},
    })


@app.post("/admin/reset_live")
def reset_live():
    """Clear demo activity (attempts + completed demo payments) without touching the dataset."""
    sender = (request.get_json(silent=True) or {}).get("sender_id")
    with connect() as con:
        if sender:  # isolate one scenario run: forget this sender's unfinished attempts
            con.execute("UPDATE attempts SET confirmed=1 WHERE sender_id=?", (sender,))
        else:
            con.execute("DELETE FROM attempts")
            con.execute("DELETE FROM transactions WHERE location='Demo'")
            pending.clear()
    return jsonify(ok=True)


@app.get("/admin/stats")
def stats():
    with connect() as con:
        counts = {r["decision"]: r["n"] for r in con.execute("SELECT decision,count(*) n FROM attempts GROUP BY decision")}
        feed = [dict(r) for r in con.execute("SELECT sender_id,receiver_id,amount,decision,risk_score,latency_ms,reasons,created_at FROM attempts ORDER BY created_at DESC LIMIT 12")]
        lat = con.execute("SELECT avg(latency_ms) a, max(latency_ms) m FROM attempts").fetchone()
        ds = con.execute("SELECT count(*) n, sum(is_fraud) f FROM dataset_transactions").fetchone() if con.execute("SELECT name FROM sqlite_master WHERE name='dataset_transactions'").fetchone() else None
    return jsonify(counts=counts, feed=feed, avg_latency_ms=round(lat["a"] or 0, 1), max_latency_ms=round(lat["m"] or 0, 1),
                   dataset={"transactions": ds["n"], "fraud": ds["f"]} if ds else None)


@app.get("/admin/model")
def model_report():
    path = REPORT_DIR / "comparison.csv"
    if not path.exists(): return jsonify(rows=[], note="Run python evaluate.py to generate the report.")
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    mix_path = REPORT_DIR / "decision_mix.csv"
    mix = list(csv.DictReader(open(mix_path))) if mix_path.exists() else []
    charts = [n for n in ("roc.png", "pr_curve.png") if (REPORT_DIR / n).exists()]
    return jsonify(rows=rows, mix=mix, charts=charts, generated=datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %Y, %H:%M"),
                   thresholds={"allow": ALLOW_THRESHOLD, "block": BLOCK_THRESHOLD, "rf_weight": RF_WEIGHT, "anomaly_weight": ANOMALY_WEIGHT,
                               "velocity_limit": VELOCITY_LIMIT})


init_db(); init_attempts()

if __name__ == "__main__":
    bundle(); baseline()  # keep model and baseline loading out of the first payment's latency
    app.run(debug=True, port=5001)
