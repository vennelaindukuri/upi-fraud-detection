"""Single live feature contract for the supplied dataset and /predict."""
import numpy as np
import pandas as pd
from config import FEATURE_COLUMNS

def live_features(sender, receiver, amount, device, now, history, user, receiver_info, is_qr=0, qr_mismatch=0):
    h=pd.DataFrame([dict(x) for x in history])
    if len(h):
        h.timestamp=pd.to_datetime(h.timestamp); past=h[h.timestamp < now]
    else: past=h
    fallback=float(user['typical_amount'])
    vals=past.amount.astype(float) if len(past) else pd.Series(dtype=float)
    mean=float(vals.mean()) if len(vals)>=5 else fallback
    std=float(vals.std()) if len(vals)>=5 else mean*.3
    std=max(std,mean*.3,1)
    cnt1=int((past.timestamp>=now-pd.Timedelta(hours=1)).sum()) if len(past) else 0
    cnt24=int((past.timestamp>=now-pd.Timedelta(hours=24)).sum()) if len(past) else 0
    receiver_rows=past[past.receiver_id==receiver] if len(past) else past
    last=past.timestamp.max() if len(past) else None
    return dict(zip(FEATURE_COLUMNS,[float(amount),now.hour,int(now.hour<5),int(is_qr),int(qr_mismatch),cnt1,cnt24,
      min((now-last).total_seconds()/60,9999) if last is not None else 9999,
      (float(amount)-mean)/std,float(amount)/max(mean,1),float(amount)/max(float(vals.max()) if len(vals) else mean,1),
      int(len(receiver_rows)==0),len(receiver_rows),int(device!=user['usual_device']),
      float(receiver_info['receiver_risk_score']) if receiver_info else 0.,float(receiver_info['account_age_days']) if receiver_info else 0.]))

def dataframe_features(df):
    return df[FEATURE_COLUMNS].astype(float).replace([np.inf,-np.inf],0).fillna(0)


LOG_COLS = ["amount", "amount_ratio", "amount_vs_max", "txn_count_1h", "txn_count_24h", "time_since_last_min",
            "receiver_pay_count", "receiver_account_age_days"]

def ae_input(X):
    """Autoencoder view of the features: money, counts and durations on a log scale (v2).
    On a raw scale every large payment looks maximally 'strange', even a genuine one."""
    Z = X.copy().astype(float)
    for c in LOG_COLS:
        Z[c] = np.log1p(Z[c].clip(lower=0))
    Z["amount_zscore"] = np.sign(Z["amount_zscore"]) * np.log1p(Z["amount_zscore"].abs())
    return Z


def blend(rf, anomaly, rf_weight=0.7, anomaly_weight=0.3, gate=0.05):
    """Final model risk (v2). The forest leads. The anomaly score only adds risk to a payment the forest
    already finds at least slightly suspicious (rf >= 5% gives the full 30%); 'unusual but clean' - e.g. a
    genuine large payment from your own phone, by day, to an established account - is not enough on its own."""
    return rf_weight * rf + anomaly_weight * anomaly * np.minimum(1.0, rf / gate)
