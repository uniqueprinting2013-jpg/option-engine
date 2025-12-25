import requests
import time
import json
import os
import pandas as pd
from datetime import datetime

# ================= CONFIG =================
REFRESH_SEC = 60
STRIKE_RANGE = 5
LEVEL_TOL = 1
SPIKE_FACTOR = 2

INDICES = {
    "NIFTY": 50,
    "BANKNIFTY": 100
}

CACHE_FILES = {
    "NIFTY": "nifty_cache.json",
    "BANKNIFTY": "banknifty_cache.json"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com"
}

session = requests.Session()

# ================= SAFE NOTIFICATION =================
def notify(title, msg):
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=msg,
            timeout=5
        )
    except:
        print(f"\n🔔 {title}\n{msg}\n")
        try:
            print('\a')  # beep
        except:
            pass


# ================= CACHE FUNCTIONS =================
def load_cache(sym):
    try:
        with open(CACHE_FILES[sym]) as f:
            return json.load(f)
    except:
        return None


def save_cache(sym, data):
    try:
        with open(CACHE_FILES[sym], "w") as f:
            json.dump(data, f)
    except:
        pass


# ================= FETCH DATA =================
def fetch(sym, expiry):
    try:
        r = session.get(
            f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={sym}&expiry={expiry}",
            headers=HEADERS,
            timeout=10
        )
        j = r.json()
        if "records" in j:
            save_cache(sym, j)
            return j, "LIVE"
    except:
        pass

    cached = load_cache(sym)
    return (cached, "CACHED") if cached else (None, "NO DATA")


def expiry(sym):
    try:
        session.get("https://www.nseindia.com", headers=HEADERS)
        r = session.get(
            f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={sym}",
            headers=HEADERS
        )
        return r.json()["records"]["expiryDates"][0]
    except:
        c = load_cache(sym)
        if c:
            return c["records"]["expiryDates"][0]
    return None


# ================= DATA PROCESS =================
def build_df(d, step):
    spot = float(d["records"]["underlyingValue"])
    atm = round(spot / step) * step

    rows = []
    for r in d["records"]["data"]:
        sp = r["strikePrice"]
        if atm - step * STRIKE_RANGE <= sp <= atm + step * STRIKE_RANGE:
            ce = r.get("CE", {})
            pe = r.get("PE", {})
            rows.append({
                "STRIKE": sp,
                "CE_OI": ce.get("openInterest", 0),
                "CE_DOI": ce.get("changeinOpenInterest", 0),
                "PE_DOI": pe.get("changeinOpenInterest", 0),
                "PE_OI": pe.get("openInterest", 0)
            })

    return pd.DataFrame(rows), atm, spot


# ================= MAIN LOOP =================
print("\n📱 ANDROID OPTION ENGINE STARTED\n")

while True:
    try:
        for sym, step in INDICES.items():
            data, mode = fetch(sym, expiry(sym))
            if not data:
                continue

            df, atm, spot = build_df(data, step)

            sup = int(df.loc[df.PE_OI.idxmax()].STRIKE)
            res = int(df.loc[df.CE_OI.idxmax()].STRIKE)

            pcr = round(df.PE_OI.sum() / df.CE_OI.sum(), 2) if df.CE_OI.sum() else 0
            dpcr = round(df.PE_DOI.sum() / df.CE_DOI.sum(), 2) if df.CE_DOI.sum() else 0

            near = df[df.STRIKE.between(atm - step, atm + step)]

            spike_pe = any(abs(near.PE_DOI) >= SPIKE_FACTOR * near.PE_DOI.abs().mean())
            spike_ce = any(abs(near.CE_DOI) >= SPIKE_FACTOR * near.CE_DOI.abs().mean())

            level = "MID"
            if abs(spot - sup) <= step * LEVEL_TOL:
                level = "SUPPORT"
            elif abs(spot - res) <= step * LEVEL_TOL:
                level = "RESISTANCE"

            signal = "WAIT"

            if level == "SUPPORT" and (spike_pe or dpcr > 1) and pcr >= 1:
                signal = "BUY"

            if level == "RESISTANCE" and (spike_ce or dpcr < 0) and pcr <= 0.9:
                signal = "SELL"

            msg = (
                f"{sym}\n"
                f"Spot: {spot}\n"
                f"Support: {sup} | Resistance: {res}\n"
                f"PCR: {pcr} | ΔPCR: {dpcr}\n"
                f"SIGNAL: {signal}"
            )

            print(f"[{datetime.now()}] {sym} → {signal}")
            notify(f"{sym} SIGNAL", msg)

    except Exception as e:
        print("ERROR:", e)

    time.sleep(REFRESH_SEC)
