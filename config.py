"""Central settings for the UPI fraud demo."""
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "upi_fraud.db"
DATA_PATH = ROOT / "data" / "transactions.csv"
MODEL_DIR = ROOT / "models" / "artifacts"
REPORT_DIR = ROOT / "reports"
RANDOM_SEED = 42

RF_WEIGHT = 0.70
ANOMALY_WEIGHT = 0.30
ALLOW_THRESHOLD = 0.25
BLOCK_THRESHOLD = 0.70
OTP_TTL_SECONDS = 60
OTP_MAX_ATTEMPTS = 3

FEATURE_COLUMNS = ["amount","hour","is_odd_hour","is_qr_payment","qr_mismatch",
 "txn_count_1h","txn_count_24h","time_since_last_min","amount_zscore","amount_ratio",
 "amount_vs_max","is_new_receiver","receiver_pay_count","is_new_device",
 "receiver_risk_score","receiver_account_age_days"]

DEMO_USERS = [
    ("ravi.demo@okshield", "Ravi", "Student", 250, "ravi-phone-01"),
    ("priya.demo@okshield", "Priya", "Shopkeeper", 3000, "priya-phone-01"),
    ("arjun.demo@okshield", "Arjun", "IT employee", 1200, "arjun-phone-01"),
    ("meena.demo@okshield", "Meena", "Homemaker", 600, "meena-phone-01"),
    ("sai.demo@okshield", "Sai", "Freelancer", 1500, "sai-phone-01"),
]
