"""Evaluate the trained model (train_models.py) on the untouched, most recent 20% of transactions.

Compares three systems on the same time-based holdout:
  * Static rules     – amount > 5,000 or (new device at night)
  * ML allow/block   – blended risk >= 0.5 is blocked
  * ML + OTP tier    – ALLOW / OTP VERIFY / BLOCK using the config thresholds.
                       OTP is assumed to be completed by genuine users and failed by fraudsters,
                       so a challenged payment ends up as its true label.
Writes reports/comparison.csv, reports/decision_mix.csv, reports/roc.png and reports/pr_curve.png.
"""
import os
os.environ.setdefault("MPLBACKEND", "Agg")
import joblib, numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (precision_recall_fscore_support, roc_auc_score, average_precision_score,
                             confusion_matrix, roc_curve, precision_recall_curve)
from config import DATA_PATH, MODEL_DIR, REPORT_DIR, RF_WEIGHT, ANOMALY_WEIGHT, ALLOW_THRESHOLD, BLOCK_THRESHOLD
from dataset_features import dataframe_features, ae_input, blend

INK, BLUE, GREY, BG = "#1C2633", "#2F5D8C", "#9AA3AD", "#F1ECE3"


def risk_scores(bundle, X):
    rf = bundle["model"].predict_proba(X)[:, 1]
    Z = bundle["scaler"].transform(ae_input(X) if bundle.get("ae_log") else X)
    err = np.mean((bundle["autoencoder"].predict(Z) - Z) ** 2, axis=1)
    an = np.clip((err - bundle["anom_lo"]) / (bundle["anom_hi"] - bundle["anom_lo"] + 1e-9), 0, 1)
    return rf, blend(rf, an, RF_WEIGHT, ANOMALY_WEIGHT)


def metrics(name, y, pred, score):
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return [name, round(p, 3), round(r, 3), round(f, 3), round(roc_auc_score(y, score), 3), round(fp / (fp + tn), 4), int(fp), int(fn)]


def main():
    REPORT_DIR.mkdir(exist_ok=True)
    d = pd.read_csv(DATA_PATH).sort_values("timestamp")
    cut = int(len(d) * .8)
    test = d.iloc[cut:].reset_index(drop=True)
    X, y = dataframe_features(test), test.is_fraud.values
    rf, risk = risk_scores(joblib.load(MODEL_DIR / "fraud_model.joblib"), X)

    rules = ((X.amount > 5000) | ((X.is_new_device == 1) & (X.is_odd_hour == 1))).astype(int).values
    binary = (risk >= .5).astype(int)
    tier = np.where(risk > BLOCK_THRESHOLD, 1, np.where(risk >= ALLOW_THRESHOLD, y, 0))
    out = pd.DataFrame([metrics("Static rules", y, rules, rules), metrics("ML allow/block", y, binary, risk), metrics("ML + OTP tier", y, tier, risk)],
                       columns=["System", "Precision", "Recall", "F1", "ROC-AUC", "False positive rate", "False blocks", "Missed fraud"])
    out.to_csv(REPORT_DIR / "comparison.csv", index=False)

    dec = np.where(risk > BLOCK_THRESHOLD, "BLOCK", np.where(risk >= ALLOW_THRESHOLD, "OTP VERIFY", "ALLOW"))
    mix = pd.crosstab(pd.Series(dec, name="decision"), pd.Series(np.where(y == 1, "fraud", "genuine"), name="truth"))
    mix.to_csv(REPORT_DIR / "decision_mix.csv")

    print(f"Holdout: {len(y):,} transactions · {int(y.sum())} fraud ({y.mean():.2%}) · "
          f"ROC-AUC {roc_auc_score(y, risk):.4f} · PR-AUC {average_precision_score(y, risk):.4f}\n")
    print(out.to_string(index=False)); print(); print(mix.to_string())
    missed = test[(dec == "ALLOW") & (y == 1)].fraud_type.value_counts()
    if len(missed): print("\nFraud that was allowed, by type:\n" + missed.to_string())

    plt.rcParams.update({"axes.facecolor": BG, "figure.facecolor": BG, "axes.edgecolor": GREY, "axes.labelcolor": INK,
                         "xtick.color": INK, "ytick.color": INK, "font.size": 10})
    fpr, tpr, _ = roc_curve(y, risk)
    plt.figure(figsize=(5, 4)); plt.plot(fpr, tpr, color=BLUE, lw=2, label=f"Blended risk · AUC {roc_auc_score(y, risk):.3f}")
    plt.plot([0, 1], [0, 1], "--", color=GREY); plt.legend(frameon=False); plt.xlabel("False positive rate"); plt.ylabel("Recall (true positive rate)")
    plt.title("ROC — time-based holdout", color=INK); plt.savefig(REPORT_DIR / "roc.png", bbox_inches="tight", dpi=150); plt.close()
    pr, re, _ = precision_recall_curve(y, risk)
    plt.figure(figsize=(5, 4)); plt.plot(re, pr, color=BLUE, lw=2, label=f"PR-AUC {average_precision_score(y, risk):.3f}")
    plt.legend(frameon=False); plt.xlabel("Recall"); plt.ylabel("Precision"); plt.title("Precision–recall — time-based holdout", color=INK)
    plt.savefig(REPORT_DIR / "pr_curve.png", bbox_inches="tight", dpi=150); plt.close()


if __name__ == "__main__":
    main()
