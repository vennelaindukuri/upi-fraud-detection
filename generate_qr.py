"""Generate safe, fictional UPI QR images for the demo QR gallery."""
from pathlib import Path
import qrcode
from config import ROOT
from db import connect

OUT = ROOT / "static" / "qr"

def write(name, payload):
    qrcode.make(payload).save(OUT / f"{name}.png")

def generate():
    OUT.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        rows = con.execute("SELECT upi_id,name,category FROM receivers").fetchall()
    for r in rows:
        write(r["upi_id"].split("@")[0], f"upi://pay?pa={r['upi_id']}&pn={r['name']}&am=500")
    write("tampered-name", "upi://pay?pa=cashback-offer.demo@okshield&pn=National%20Bank%20Cashback&am=500")
    write("tampered-malformed", "not-a-upi-payment?free-money=yes")
    write("tampered-brand", "upi://pay?pa=refund-support.demo@okshield&pn=Official%20UPI%20Refund%20Desk&am=2000")
    print(f"Generated {len(rows)+3} demo QR images in {OUT}")

if __name__ == "__main__": generate()
