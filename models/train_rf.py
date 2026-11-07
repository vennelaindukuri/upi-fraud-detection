"""Train calibrated Random Forest and an anomaly model on genuine transactions."""
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from config import DATA_PATH, MODEL_DIR, FEATURE_COLUMNS, RANDOM_SEED
from features import build_training_features


def train():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(DATA_PATH).sort_values("timestamp").reset_index(drop=True)
    X = build_training_features(data).replace([np.inf, -np.inf], 0).fillna(0)
    y = data.is_fraud.astype(int)
    # Chronological holdout preserves a realistic validation distribution.
    cut = int(len(X) * .8); X_train, X_val = X.iloc[:cut], X.iloc[cut:]; y_train, y_val = y.iloc[:cut], y.iloc[cut:]
    rf = RandomForestClassifier(n_estimators=120, max_depth=16, min_samples_leaf=3, class_weight="balanced", n_jobs=-1, random_state=RANDOM_SEED)
    calibrated = CalibratedClassifierCV(rf, method="sigmoid", cv=3)
    calibrated.fit(X_train, y_train)
    scaler = RobustScaler().fit(X_train)
    genuine = scaler.transform(X_train[y_train == 0])
    # Isolation Forest is a compact reconstruction-style anomaly proxy for this CPU-first demo.
    anomaly = IsolationForest(n_estimators=100, contamination=.03, random_state=RANDOM_SEED, n_jobs=-1).fit(genuine)
    raw = -anomaly.score_samples(scaler.transform(X_train))
    lo, hi = np.percentile(raw, [1, 99])
    joblib.dump({"model":calibrated, "scaler":scaler, "anomaly":anomaly, "anom_lo":float(lo), "anom_hi":float(hi), "features":FEATURE_COLUMNS}, MODEL_DIR / "fraud_model.joblib")
    p = calibrated.predict_proba(X_val)[:,1]
    print(f"Saved model. Validation RF ROC-AUC: {roc_auc_score(y_val, p):.3f}")
    return X, y, cut

if __name__ == "__main__": train()
