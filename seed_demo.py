"""Reset and seed the entirely fictional @okshield UPI demo ecosystem."""
import random
import uuid
from datetime import datetime, timedelta
from config import DEMO_USERS, RANDOM_SEED
from db import connect, reset_demo_tables

MERCHANTS = [
    ("chaiwala.demo@okshield", "Chai Wala", 50), ("freshmart.demo@okshield", "Fresh Mart", 800),
    ("campuscanteen.demo@okshield", "Campus Canteen", 120), ("metrorecharge.demo@okshield", "Metro Recharge", 300),
    ("citypharmacy.demo@okshield", "City Pharmacy", 450), ("fuelpoint.demo@okshield", "Fuel Point", 1500),
]
FRIENDS = [("anil.demo@okshield", "Anil", 500), ("sneha.demo@okshield", "Sneha", 400)]
SUSPICIOUS = [
    ("refund-support.demo@okshield", "Refund Support", "fake refund scam"),
    ("lucky-draw99.demo@okshield", "Lucky Draw", "prize scam, newly created"),
    ("kyc-update.demo@okshield", "KYC Update", "phishing-style"),
    ("cashback-offer.demo@okshield", "Cashback Offer", "mismatched name in QR"),
]


def seed():
    random.seed(RANDOM_SEED)
    reset_demo_tables()
    extras = [(f"localshop{i:02d}.demo@okshield", f"Local Shop {i:02d}", random.choice([80, 150, 300, 650, 1000])) for i in range(1, 51)]
    with connect() as con:
        con.executemany("INSERT INTO users VALUES (?,?,?,?,?)", DEMO_USERS)
        con.executemany("INSERT INTO receivers (upi_id,name,typical_amount,category,is_flagged,receiver_risk,qr_name) VALUES (?,?,?,'merchant',0,0,?)", [(u,n,a,n) for u,n,a in MERCHANTS + extras])
        con.executemany("INSERT INTO receivers (upi_id,name,typical_amount,category,is_flagged,receiver_risk,qr_name) VALUES (?,?,?,'friend',0,0,?)", [(u,n,a,n) for u,n,a in FRIENDS])
        con.executemany("INSERT INTO receivers (upi_id,name,typical_amount,category,is_flagged,receiver_risk,qr_name) VALUES (?,?,0,'suspicious',1,.92,?)", [(u,n,n) for u,n,_ in SUSPICIOUS])
        start = datetime.now().replace(second=0, microsecond=0) - timedelta(days=28)
        rows=[]
        for upi, name, role, typical, device in DEMO_USERS:
            # Each person retains a small stable set of regular payees and daytime habit.
            regular = random.sample(MERCHANTS + FRIENDS, 4)
            for day in range(28):
                for _ in range(random.randint(2,4)):
                    receiver, _, base = random.choice(regular)
                    hour = int(max(8,min(21,random.gauss(13,2.2))))
                    ts = start + timedelta(days=day, hours=hour, minutes=random.randrange(60))
                    amount = max(10, round(random.lognormvariate(0,.28) * min(max(base, typical*.45), typical*1.25), 2))
                    rows.append((str(uuid.uuid4()),upi,receiver,amount,ts.isoformat(sep=' '),hour,device,'Demo City',0,0,'ALLOW',0,0))
        con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"Seeded {len(DEMO_USERS)} fictional users, {len(MERCHANTS)+len(FRIENDS)+len(SUSPICIOUS)+len(extras)} receivers, and {len(rows)} historical payments.")

if __name__ == "__main__": seed()
