"""One-command bootstrap: data, SQLite history, and trained artifacts."""
from config import DATA_PATH
from generate_data import generate
from db import init_db, seed_from_csv
from models.train_rf import train

if __name__ == "__main__":
    if not DATA_PATH.exists(): generate()
    init_db(); seed_from_csv(DATA_PATH)
    train()
    print("Setup complete. Start the demo with: python app.py")
