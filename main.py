import os
import time
import threading
import warnings
import logging
import json
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import pytz

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELE_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8659453018"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@KEVINTRAILBLAZE")
LAGOS_TZ = pytz.timezone("Africa/Lagos")

WELCOME_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
INTRO_PHOTO = "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=1080&q=80"
READY_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

ENABLE_OTC = True
AUTO_TRADE_ENABLED = False
MAX_DAILY_TRADES = 30
MIN_CONFIDENCE = 88.0

REAL_NGN_BASE = 1400.0
PRACTICE_USD_BASE = 1.0
MARTINGALE_MULTIPLIERS = [1, 2, 4, 8]  # REAL NGN: 1400 -> 2800 -> 5600 -> 11200 then reset

REAL_PAIRS = [
    "EURUSD", "GBPUSD", "EURGBP", "AUDUSD", "USDCAD",
    "USDCHF", "EURAUD", "GBPCHF", "EURCHF", "NZDUSD",
    "GBPAUD", "EURCAD", "AUDCAD", "GBPCAD", "AUDNZD",
]
OTC_PAIRS = [
    "EURUSD-OTC", "GBPUSD-OTC","EURGBP-OTC"
]
PAIR_EMOJI = {
    "EURUSD": "🇪🇺 EUR/USD REAL", "GBPUSD": "🇬🇧 GBP/USD REAL", "EURGBP": "🇪🇺 EUR/GBP REAL",
    "AUDUSD": "🇦🇺 AUD/USD REAL", "USDCAD": "🇺🇸 USD/CAD REAL", "USDCHF": "🇺🇸 USD/CHF REAL",
    "EURAUD": "🇪🇺 EUR/AUD REAL", "GBPCHF": "🇬🇧 GBP/CHF REAL", "EURCHF": "🇪🇺 EUR/CHF REAL",
    "NZDUSD": "🇳🇿 NZD/USD REAL", "GBPAUD": "🇬🇧 GBP/AUD REAL", "EURCAD": "🇪🇺 EUR/CAD REAL",
    "AUDCAD": "🇦🇺 AUD/CAD REAL", "GBPCAD": "🇬🇧 GBP/CAD REAL", "AUDNZD": "🇦🇺 AUD/NZD REAL",
    "EURUSD-OTC": "🇪🇺 EUR/USD OTC", "GBPUSD-OTC": "🇬🇧 GBP/USD OTC", "EURGBP-OTC": "🇪🇺 EUR/GBP OTC",
    "AUDUSD-OTC": "🇦🇺 AUD/USD OTC", "USDCHF-OTC": "🇺🇸 USD/CHF OTC", "EURAUD-OTC": "🇪🇺 EUR/AUD OTC",
    "GBPAUD-OTC": "🇬🇧 GBP/AUD OTC", "NZDUSD-OTC": "🇳🇿 NZD/USD OTC", "GBPCHF-OTC": "🇬🇧 GBP/CHF OTC",
    "EURCHF-OTC": "🇪🇺 EUR/CHF OTC", "USDCAD-OTC": "🇺🇸 USD/CAD OTC", "AUDCAD-OTC": "🇦🇺 AUD/CAD OTC",
    "EURCAD-OTC": "🇪🇺 EUR/CAD OTC",
}

WELCOME_TEXT = (
    "🔥🔥🔥 WELCOME TO TRAILBLAZER SIGNALS 🔥🔥🔥\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "👋 Welcome Trader! You have arrived at the right place.\n\n"
    "🥇 WHAT WE DO HERE\n"
    "📈 Forex Sniper Signals\n"
    "🎯 88%+ Accuracy Only\n"
    "🧠 Smart System That Learns From Every Win and Loss\n"
    "💰 Martingale 1-2-4-8 (₦1,400 -> ₦2,800 -> ₦5,600 -> ₦11,200) To Recover Losses\n\n"
    "📜 CHANNEL RULES\n"
    "✅ 1. Follow The Stake - ₦1,400, ₦2,800, ₦5,600, ₦11,200 ($1, $2, $4, $8) - Do Not Be Greedy\n"
    "✅ 2. Do Not Overtrade - Maximum 30 Signals Per Day\n"
    "✅ 3. Enter Exactly At The Entry Time\n"
    "✅ 4. Press WIN or LOSS After Every Trade\n"
    "❌ 5. No Spam, No Direct Message To Admin For Signals\n"
    "❌ 6. Do Not Borrow Money To Trade\n\n"
    "🚀 NEW HERE? Type /intro For A Full Guide\n"
    "📊 Type /status To See Today's Result\n"
    "📢 Channel: @KEVINTRAILBLAZE\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💪 Good Luck Trader! Let Us Grow Together! 🤑\n"
    "🏆 TRAILBLAZER - WE MOVE! 🔥"
)

INTRO_TEXT = (
    "📚📚 TRAILBLAZER INTRO 📚📚\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💱 WHAT IS FOREX?\n"
    "Forex Means Foreign Exchange. You Predict If One Currency Will Go UP ⬆️ Or DOWN ⬇️ Against Another.\n"
    "Example: EUR/USD - Euro Against Dollar.\n"
    "If Euro Is Strong, Press BUY / CALL 🟢\n"
    "If Euro Is Weak, Press SELL / PUT 🔴\n\n"
    "📈 HOW DO YOU MAKE MONEY?\n"
    "1️⃣ Enter With A Stake For Example ₦1,400 ($1)\n"
    "2️⃣ If You Are Correct, IQ Option Pays You ~85% Back 🤑\n"
    "3️⃣ If You Are Wrong, We Use Martingale ₦1,400 ➡️ ₦2,800 ➡️ ₦5,600 ➡️ ₦11,200 To Recover\n\n"
    "🚀 HOW TO START ON IQ OPTION\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "1️⃣ CREATE ACCOUNT\n"
    "Go To iqoption.com -> Sign Up -> Email And Password\n\n"
    "2️⃣ VERIFY EMAIL 📧\n"
    "Open Your Email, Click The Verification Link\n\n"
    "3️⃣ PRACTICE WITH DEMO 🎮\n"
    "IQ Option Will Give You $10,000 DEMO. Practice For 2 To 3 Days, No Real Money.\n\n"
    "4️⃣ VERIFY ACCOUNT (KYC) 🪪\n"
    "Profile -> Verification -> Upload ID And Selfie\n\n"
    "5️⃣ DEPOSIT 💳\n"
    "Deposit -> Card / Bank / USDT -> Start With At Least ₦21,000 ($15)\n\n"
    "6️⃣ TRADE WITH US 🔥\n"
    "Open IQ Option App -> EUR/USD -> Wait For Signal -> Enter At ENTRY TIME\n\n"
    "⚠️ RULES:\n"
    "• No Overtrade - Maximum 30 Per Day\n"
    "• Follow Stake - ₦1,400, ₦2,800, ₦5,600, ₦11,200\n"
    "• Trading Has Risk, Only Trade Money You Can Afford To Lose\n\n"
    "📢 Channel: @KEVINTRAILBLAZE\n"
    "👋 Welcome Again! Let Us Go! 🚀"
)

STATS = {"balance": 0.0, "real_balance": 0.0, "wins": 0, "loss": 0, "streak": 0, "daily_trades": 0, "daily_date": ""}
user_states = {}
AUTO_STATE = {}
IQ_LOCK = threading.Lock()
SIGNAL_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()
IQ_CONNECTED = False
iq = None
PAYOUT_CACHE = {}
PAYOUT_TIME = 0.0
OTC_SESSION_RESULTS = []
OTC_MARTI = {
    "loss_streak": 0,
    "base": PRACTICE_USD_BASE,
    "bal": "PRACTICE",
    "currency": "USD",
    "levels": MARTINGALE_MULTIPLIERS,
}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {
    "active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0,
    "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120
}
POST_SESSION_REST_SEC = 180  # 3 minutes after signal + pullback martingale ends
SKIP_COOLDOWN = 120
SESSION_STATE = {
    "active": False,
    "in_pullback": False,
    "rest_until": 0.0,
}
LAST_GLOBAL_SIGNAL = {"time": 0.0}
DAILY_SUMMARY_SENT = ""
MARKET_GOOD_SENT = {"date": "", "last_alert": 0.0}
MORNING_GREET_SENT = ""
NEWS_CACHE = {"data": [], "time": 0.0}
PAIR_BRAIN = {}


def is_real_mode() -> bool:
    return str(OTC_MARTI.get("bal", "PRACTICE")).upper() == "REAL"


def sync_currency_config():
    """Enforces NGN (1400 -> 2800 -> 5600 -> 11200) on REAL and USD (1 -> 2 -> 4 -> 8) on PRACTICE."""
    if is_real_mode():
        OTC_MARTI["bal"] = "REAL"
        OTC_MARTI["currency"] = "NGN"
        OTC_MARTI["base"] = REAL_NGN_BASE
    else:
        OTC_MARTI["bal"] = "PRACTICE"
        OTC_MARTI["currency"] = "USD"
        OTC_MARTI["base"] = PRACTICE_USD_BASE


def get_active_currency_symbol() -> str:
    return "₦" if is_real_mode() else "$"


def format_money(amount: float) -> str:
    if is_real_mode():
        return f"₦{float(amount):,.0f}"
    return f"${float(amount):,.2f}"


def get_martingale_sequence_str() -> str:
    base = REAL_NGN_BASE if is_real_mode() else PRACTICE_USD_BASE
    return " -> ".join(format_money(base * m) for m in OTC_MARTI["levels"])


def get_current_stake() -> float:
    sync_currency_config()
    idx = max(0, min(OTC_MARTI["loss_streak"], len(OTC_MARTI["levels"]) - 1))
    return round(OTC_MARTI["base"] * OTC_MARTI["levels"][idx], 2)


def get_lagos_now():
    return datetime.now(LAGOS_TZ)


def get_lagos_day():
    return get_lagos_now().strftime("%Y-%m-%d")


def is_allowed(uid):
    return uid == OWNER_ID


def is_real_hours():
    try:
        now = get_lagos_now()
        if now.weekday() >= 5:
            return False
        return 7 <= now.hour < 20
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        if now.weekday() >= 5:
            return False
        return 7 <= now.hour < 20


def get_rest_remaining() -> float:
    with SESSION_LOCK:
        return max(0.0, SESSION_STATE["rest_until"] - time.time())


def is_in_post_session_rest() -> bool:
    return get_rest_remaining() > 0.0


def begin_trading_session():
    with SESSION_LOCK:
        SESSION_STATE["active"] = True
        SESSION_STATE["in_pullback"] = False
        SESSION_STATE["rest_until"] = 0.0


def set_pullback_active(active: bool):
    with SESSION_LOCK:
        SESSION_STATE["in_pullback"] = active


def finish_trading_session_and_rest(rest_seconds: int = POST_SESSION_REST_SEC):
    now_ts = time.time()
    with SESSION_LOCK:
        SESSION_STATE["active"] = False
        SESSION_STATE["in_pullback"] = False
        SESSION_STATE["rest_until"] = now_ts + rest_seconds
    LAST_GLOBAL_SIGNAL["time"] = now_ts
    clear_signal()


def get_mode_text():
    sync_currency_config()
    mode = "AUTO-TRADE" if AUTO_TRADE_ENABLED else "MANUAL SIGNAL"
    bal = f"{OTC_MARTI['bal']} ({OTC_MARTI['currency']})"
    otc_txt = "OTC: ON" if ENABLE_OTC else "OTC: OFF"
    sess = "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OUTSIDE REAL HOURS (7AM-8PM)"
    rest_rem = int(get_rest_remaining())
    rest_txt = f" | REST {rest_rem}s" if rest_rem > 0 else ""
    return f"{mode} | {otc_txt} | {bal} | {sess}{rest_txt}"


def check_and_reset_new_day():
    today = get_lagos_day()
    if STATS["daily_date"] != today:
        STATS["daily_date"] = today
        STATS["daily_trades"] = 0
        ACTIVE_SIGNAL.update({
            "active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0,
            "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120
        })
        PULLBACK_STATE.clear()
        OTC_MARTI["loss_streak"] = 0
        with SESSION_LOCK:
            SESSION_STATE["active"] = False
            SESSION_STATE["in_pullback"] = False
            SESSION_STATE["rest_until"] = 0.0
        return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("day") and ACTIVE_SIGNAL["day"] != today:
        ACTIVE_SIGNAL.update({
            "active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0,
            "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120
        })
        PULLBACK_STATE.clear()
        OTC_MARTI["loss_streak"] = 0
        with SESSION_LOCK:
            SESSION_STATE["active"] = False
            SESSION_STATE["in_pullback"] = False
            SESSION_STATE["rest_until"] = 0.0
        return True
    return False


def can_trade_today():
    check_and_reset_new_day()
    return STATS["daily_trades"] < MAX_DAILY_TRADES


def count_trade():
    check_and_reset_new_day()
    STATS["daily_trades"] += 1


def is_signal_active():
    check_and_reset_new_day()
    with SESSION_LOCK:
        if SESSION_STATE["active"] or SESSION_STATE["in_pullback"]:
            return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("started"):
        max_age = max(ACTIVE_SIGNAL.get("expiry", 120) + 900, 1200)
        if time.time() - ACTIVE_SIGNAL["started"] > max_age:
            finish_trading_session_and_rest(POST_SESSION_REST_SEC)
    return ACTIVE_SIGNAL["active"]


def can_start_new_scan_or_signal() -> bool:
    check_and_reset_new_day()
    if not can_trade_today():
        return False
    if is_signal_active():
        return False
    with SESSION_LOCK:
        if SESSION_STATE["active"] or SESSION_STATE["in_pullback"]:
            return False
        if time.time() < SESSION_STATE["rest_until"]:
            return False
    return True


def start_signal(pair, dir_, conf=0, rsi=0, adx=0, price=0, sl=0, tp1=0, tp2=0, expiry=120):
    check_and_reset_new_day()
    ACTIVE_SIGNAL.update({
        "active": True, "pair": pair, "dir": dir_, "conf": conf, "rsi": rsi,
        "adx": adx, "started": time.time(), "day": get_lagos_day(), "price": price,
        "sl": sl, "tp1": tp1, "tp2": tp2, "expiry": expiry
    })
    begin_trading_session()


def clear_signal():
    ACTIVE_SIGNAL.update({
        "active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0,
        "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 120
    })


def load_brain():
    global PAIR_BRAIN
    try:
        with open("brain.json", "r") as f:
            PAIR_BRAIN = json.load(f)
    except Exception:
        PAIR_BRAIN = {}


def save_brain():
    try:
        with open("brain.json", "w") as f:
            json.dump(PAIR_BRAIN, f)
    except Exception:
        pass


def get_pair_stats(pair):
    if pair not in PAIR_BRAIN:
        PAIR_BRAIN[pair] = {
            "wins": 0, "loss": 0, "history": [], "blocked_until": 0, "score_boost": 0,
            "hour_stats": {}, "rsi_wins": [], "rsi_loss": [],
            "best_hour": None, "worst_hour": None, "best_rsi_range": None
        }
    s = PAIR_BRAIN[pair]
    s.setdefault("hour_stats", {})
    s.setdefault("rsi_wins", [])
    s.setdefault("rsi_loss", [])
    s.setdefault("history", [])
    s.setdefault("blocked_until", 0)
    s.setdefault("score_boost", 0)
    return s


def get_pair_winrate(pair):
    s = get_pair_stats(pair)
    total = s["wins"] + s["loss"]
    if total < 3:
        return None
    return s["wins"] / total * 100


def is_pair_blocked(pair):
    s = get_pair_stats(pair)
    return time.time() < s.get("blocked_until", 0)


def record_brain(pair, won, conf, rsi, adx):
    s = get_pair_stats(pair)
    hour = str(get_lagos_now().hour)
    if won:
        s["wins"] += 1
        STATS["streak"] = STATS["streak"] + 1 if STATS["streak"] >= 0 else 1
    else:
        s["loss"] += 1
        STATS["streak"] = STATS["streak"] - 1 if STATS["streak"] <= 0 else -1

    s["hour_stats"].setdefault(hour, {"wins": 0, "loss": 0})
    if won:
        s["hour_stats"][hour]["wins"] += 1
        s["rsi_wins"].append(rsi)
    else:
        s["hour_stats"][hour]["loss"] += 1
        s["rsi_loss"].append(rsi)

    s["rsi_wins"] = s["rsi_wins"][-30:]
    s["rsi_loss"] = s["rsi_loss"][-30:]
    s["history"].append({
        "win": won, "conf": conf, "rsi": rsi, "adx": adx,
        "time": time.time(), "hour": hour
    })
    s["history"] = s["history"][-30:]

    best_h = None
    best_wr = 0.0
    worst_h = None
    worst_wr = 100.0
    for h, st in s["hour_stats"].items():
        total = st["wins"] + st["loss"]
        if total >= 3:
            wr = st["wins"] / total * 100
            if wr > best_wr:
                best_wr = wr
                best_h = h
            if wr < worst_wr:
                worst_wr = wr
                worst_h = h
    s["best_hour"] = best_h
    s["worst_hour"] = worst_h

    if len(s["rsi_wins"]) >= 5:
        avg_win_rsi = sum(s["rsi_wins"]) / len(s["rsi_wins"])
        s["best_rsi_range"] = [avg_win_rsi - 7, avg_win_rsi + 7]

    wr = get_pair_winrate(pair)
    total = s["wins"] + s["loss"]
    if wr is not None and total >= 5:
        if wr < 40:
            s["blocked_until"] = time.time() + 7200
            s["score_boost"] = -15
        elif wr < 50:
            s["score_boost"] = -8
        elif wr >= 65:
            s["score_boost"] = 8
            s["blocked_until"] = 0
        elif wr >= 55:
            s["score_boost"] = 3
        else:
            s["score_boost"] = 0
    save_brain()


def get_hour_boost(pair):
    s = get_pair_stats(pair)
    hour = str(get_lagos_now().hour)
    st = s.get("hour_stats", {}).get(hour)
    if not st:
        return 0, ""
    total = st["wins"] + st["loss"]
    if total < 3:
        return 0, ""
    wr = st["wins"] / total * 100
    if wr >= 70:
        return 8, f"🧠 Best Hour {hour}:00 {wr:.0f}%"
    if wr >= 60:
        return 4, f"🧠 Good Hour {hour}:00 {wr:.0f}%"
    if wr < 40:
        return -10, f"🧠 Bad Hour {hour}:00 {wr:.0f}%"
    if wr < 50:
        return -5, f"🧠 Weak Hour {hour}:00 {wr:.0f}%"
    return 0, ""


def get_pair_rsi_boost(pair, current_rsi):
    s = get_pair_stats(pair)
    rng = s.get("best_rsi_range")
    if not rng or len(s.get("rsi_wins", [])) < 5:
        return 0, ""
    low, high = rng
    if low <= current_rsi <= high:
        return 6, f"🧠 RSI Sweet Spot {current_rsi:.0f}"
    dist = min(abs(current_rsi - low), abs(current_rsi - high))
    if dist > 15:
        return -6, f"🧠 RSI Off {current_rsi:.0f}"
    return 0, ""


load_brain()


def send_to_channel_sync(text):
    try:
        bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"channel send err {e}")


def send_photo_to_channel_sync(photo_url, caption):
    try:
        bot.send_photo(CHANNEL_ID, photo_url, caption=caption, parse_mode="Markdown")
    except Exception as e:
        print(f"photo channel err {e}")
        try:
            bot.send_message(CHANNEL_ID, caption, parse_mode="Markdown")
        except Exception:
            pass


def format_channel_signal(pair, dir_, conf, price, entry_time_txt, expiry=120):
    if dir_ == "CALL":
        action = "🟢 BUY / CALL ⬆️"
        meaning = "The Price Is Expected To Go UP, So Press The GREEN BUY / CALL Button In IQ Option"
    else:
        action = "🔴 SELL / PUT ⬇️"
        meaning = "The Price Is Expected To Go DOWN, So Press The RED SELL / PUT Button In IQ Option"
    pair_name = PAIR_EMOJI.get(pair, pair)
    price_txt = f"{price:.5f}" if price and price != 0 else "Market Price"
    expiry_min = max(1, int(expiry // 60)) if expiry else 2
    return f"""🔥🔥🔥 TRAILBLAZER SIGNAL 🔥🔥🔥

💱 Pair: {pair_name}
📊 Signal: {action}
🎯 Confidence: {conf:.0f}%

💡 What It Means:
{meaning}

━━━━━━━━━━━━━━━━━━
⏰ ENTRY TIME: {entry_time_txt}
💰 ENTRY PRICE: {price_txt}
💵 STAKE: ₦1,400 / $1 (Next: ₦2,800 / $2 -> ₦5,600 / $4 -> ₦11,200 / $8)
⏱️ EXPIRY: {expiry_min} Minutes - Use The Same Expiry As Shown Here
━━━━━━━━━━━━━━━━━━

👣 HOW TO TRADE THIS SIGNAL (STEP BY STEP):
1️⃣ Open The IQ Option App
2️⃣ Search For {pair}
3️⃣ Wait Until The Time Reaches {entry_time_txt}
4️⃣ Set Expiry To {expiry_min} Minutes
5️⃣ Press {action}
6️⃣ Enter With ₦1,400 ($1) And Wait For {expiry_min} Minutes

⚠️ RULES:
✅ Enter Exactly At The Entry Time, Do Not Enter Late
✅ Do Not Be Greedy - Follow ₦1,400, ₦2,800, ₦5,600, ₦11,200 ($1, $2, $4, $8) Only
✅ If You Win, Go Back To ₦1,400 ($1)
❌ Do Not Overtrade

📢 Channel: @KEVINTRAILBLAZE
Good Luck! 💪🤑
"""


def format_channel_pullback_signal(pair, dir_, entry_time_txt, level_idx=1, amount=2800.0, expiry=120):
    action = "🟢 BUY / CALL ⬆️" if dir_ == "CALL" else "🔴 SELL / PUT ⬇️"
    pair_name = PAIR_EMOJI.get(pair, pair)
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    level_name = level_names[level_idx] if 1 <= level_idx <= 3 else f"Martingale {level_idx}"
    expiry_min = max(1, int(expiry // 60)) if expiry else 2
    mult = OTC_MARTI["levels"][level_idx] if 0 <= level_idx < len(OTC_MARTI["levels"]) else 2
    ngn_amt = REAL_NGN_BASE * mult
    usd_amt = PRACTICE_USD_BASE * mult
    return f"""🔁 {level_name.upper()} - {pair_name}

📊 {action}
⏰ Entry: {entry_time_txt}
💵 Stake: ₦{ngn_amt:,.0f} (${usd_amt:.0f})
⏱️ Expiry: {expiry_min} Min

👉 Open IQ Option -> Search {pair} -> Press {action} At Entry Time.

📢 @KEVINTRAILBLAZE
"""


def get_greeting():
    hour = get_lagos_now().hour
    if 5 <= hour < 12:
        return "🌅 GOOD MORNING TRAILBLAZER ☀️"
    if 12 <= hour < 17:
        return "☀️ GOOD AFTERNOON TRAILBLAZER 🔥"
    if 17 <= hour < 21:
        return "🌇 GOOD EVENING TRAILBLAZER 🌙"
    return "🌙 GOOD NIGHT TRAILBLAZER 💤"


def get_greeting_msg():
    hour = get_lagos_now().hour
    if 5 <= hour < 12:
        return "🌅 Rise And Shine! A New Day, New Money To Earn 💰\n☕ Grab Your Coffee, The Market Is Waking Up!"
    if 12 <= hour < 17:
        return "☀️ Afternoon Session! The Market Is Active 🔥\n💪 Stay Focused, Trailblazer!"
    if 17 <= hour < 21:
        return "🌇 Evening Session! Last Chance To Earn Before The Market Closes 🌙\n🎯 Let Us Finish Strong!"
    return "🌙 The Market Is Resting. Rest Your Mind, Trailblazer 💤\n💰 Tomorrow We Earn Again!"


def get_session_boost(pair):
    now = get_lagos_now()
    hour = now.hour + now.minute / 60.0
    if "-OTC" in pair:
        return 4, "⚡ OTC ACTIVE"
    if 8 <= hour < 11:
        if pair[:3] in ["EUR", "GBP", "CHF"] or pair[3:6] in ["EUR", "GBP", "CHF"]:
            return 8, "🇬🇧 LONDON OPEN"
        return 6, "🇬🇧 LONDON OPEN"
    if 14.5 <= hour < 17:
        return 10, "🇬🇧🇺🇸 LONDON + NY OVERLAP 🔥"
    if 14 <= hour < 14.5:
        return 4, "🇺🇸 NY PRE-OPEN"
    if 12 <= hour < 13.5:
        return -10, "😴 LUNCH DEAD ZONE"
    if 18 <= hour < 20:
        return -5, "🌙 EVENING SLOW"
    if 11 <= hour < 12:
        return 3, "🇬🇧 LONDON MORNING"
    if 17 <= hour < 18:
        return 2, "🇺🇸 NY AFTERNOON"
    return 0, "🌍 NORMAL"


def get_upcoming_news():
    try:
        if time.time() - NEWS_CACHE["time"] < 300:
            return NEWS_CACHE["data"]
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return NEWS_CACHE["data"]
        root = ET.fromstring(r.content)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        upcoming = []
        for event in root.findall("event"):
            try:
                title = (event.find("title").text or "").strip()
                country = (event.find("country").text or "").strip()
                impact = (event.find("impact").text or "").strip()
                date_str = (event.find("date").text or "").strip()
                time_str = (event.find("time").text or "").strip()
                if impact != "High":
                    continue
                if country not in ["USD", "EUR", "GBP", "AUD", "CAD", "NZD", "CHF"]:
                    continue
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                dt_utc = dt + timedelta(hours=5)
                diff_min = (dt_utc - now).total_seconds() / 60.0
                if -15 <= diff_min <= 120:
                    upcoming.append({
                        "title": title, "country": country, "time_utc": dt_utc,
                        "in_min": int(diff_min), "impact": impact
                    })
            except Exception:
                continue
        NEWS_CACHE["data"] = upcoming
        NEWS_CACHE["time"] = time.time()
        return upcoming
    except Exception:
        return NEWS_CACHE["data"]


def is_news_blocking_pair(pair, minutes=30):
    if "-OTC" in pair:
        return None
    news = get_upcoming_news()
    if not news:
        return None
    base, quote = pair[:3], pair[3:6] if len(pair) >= 6 else ""
    for n in news:
        if n["country"] in [base, quote] and -15 <= n["in_min"] <= minutes:
            return n
    return None


def get_ready_text():
    now = get_lagos_now()
    _, sn = get_session_boost("EURUSD")
    news = get_upcoming_news()
    news_txt = (
        "✅ No High Impact News In Next 2 Hours - Clean Market"
        if not news
        else f"⚠️ {len(news)} High Impact News In Next 2 Hours - Bot Will Avoid Those Pairs"
    )
    return f"""🚀🚀🚀 GET READY TRAILBLAZERS 🚀🚀🚀

{get_greeting()}

⏰ Time: {now.strftime('%A, %d %b %Y - %H:%M WAT')}
⏰ Session: {sn}
📊 Mode: {get_mode_text()}
📰 News: {news_txt}
📅 Today: {STATS['daily_trades']}/{MAX_DAILY_TRADES} Trades Used

━━━━━━━━━━━━━━━━━━
✅ CHECKLIST - DO THIS NOW BEFORE SIGNALS START:
━━━━━━━━━━━━━━━━━━

1️⃣ OPEN IQ OPTION APP 📱
Open Your IQ Option App Now. Do Not Wait For The Signal To Open It.

2️⃣ CHECK YOUR BALANCE 💰
Make Sure You Have At Least ₦21,000 ($15 To $20) In Your Account.
If You Are On DEMO, Make Sure You Have $1,000+ Demo Balance.

3️⃣ CHECK YOUR INTERNET 🌐
Use Strong WiFi Or Mobile Data. A Slow Connection Can Make You Enter Late.

4️⃣ CHARGE YOUR PHONE 🔋
Charge Your Phone To At Least 50%. Do Not Miss A Signal Because Your Phone Died.

5️⃣ SET YOUR STAKE TO ₦1,400 ($1) 💵
Go To IQ Option -> Amount -> Set It To ₦1,400 ($1).
We Will Use Martingale: ₦1,400 -> ₦2,800 -> ₦5,600 -> ₦11,200 ($1 -> $2 -> $4 -> $8) If We Lose.

6️⃣ SET YOUR CHART TO 1 MINUTE 📊
For Forex Signals, Use 1 Minute Candles.

7️⃣ CLEAR YOUR MIND 🧠
No Distractions. Focus Only On The Signals.
Do Not Trade Other Pairs That We Did Not Call.

━━━━━━━━━━━━━━━━━━
📋 HOW TODAY WILL WORK:
━━━━━━━━━━━━━━━━━━
🎯 Only 88%+ Sniper Signals
💱 15 Forex Pairs + OTC Pairs
⏱️ Expiry Will Be Shown On Each Signal - Use The Exact Expiry
⏰ Enter Exactly At The Entry Time Shown
✅ If You WIN - Go Back To ₦1,400 ($1)
❌ If You LOSE - Wait For Martingale Signal (₦2,800, ₦5,600, ₦11,200)
⏭️ If You Miss A Signal - Skip It, Do Not Chase It

━━━━━━━━━━━━━━━━━━
⚠️ RULES FOR TODAY:
━━━━━━━━━━━━━━━━━━
✅ Follow The Stake - ₦1,400, ₦2,800, ₦5,600, ₦11,200 Only
✅ Maximum 30 Trades Today
✅ Enter At Entry Time Only
❌ Do Not Be Greedy - Do Not Increase Stake On Your Own
❌ Do Not Trade If You Are Angry Or Tired
❌ Do Not Borrow Money To Trade

━━━━━━━━━━━━━━━━━━
🔥 SIGNALS ARE COMING SOON - STAY READY! 🔥
📢 Channel: @KEVINTRAILBLAZE

Drop 🔥 In The Comments If You Are Ready!
"""


def _configure_proxy(api_client):
    proxy = os.getenv("PROXY_URL")
    if not proxy:
        return
    try:
        pc = proxy.replace("http://", "").replace("https://", "")
        if "@" in pc:
            up, hp = pc.split("@", 1)
            pu, pp = up.split(":", 1)
            ph, pt = hp.split(":", 1)
            api_client.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
    except Exception:
        pass


def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(3)
    email = os.getenv("IQ_EMAIL")
    pwd = os.getenv("IQ_PASS")
    if not email or not pwd:
        print("IQ_EMAIL/PASS missing")
        return
    for _ in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                client = IQ_Option(email, pwd)
                _configure_proxy(client)
                client.connect()
                connected = bool(client.check_connect())
                if connected:
                    iq = client
                    IQ_CONNECTED = True
                    try:
                        sync_currency_config()
                        iq.change_balance(OTC_MARTI["bal"])
                        time.sleep(1)
                        bal = float(iq.get_balance() or 0.0)
                        STATS["real_balance"] = bal
                        STATS["balance"] = bal
                        print(f"[IQ] SUCCESS {format_money(bal)} ({OTC_MARTI['bal']})")
                    except Exception:
                        pass
                    return
            IQ_CONNECTED = False
            time.sleep(8)
        except Exception as e:
            print(f"[IQ] Fail {e}")
            IQ_CONNECTED = False
            time.sleep(10)


def iq_reconnect():
    global iq, IQ_CONNECTED
    email = os.getenv("IQ_EMAIL")
    pwd = os.getenv("IQ_PASS")
    if not email or not pwd:
        return False
    try:
        from iqoptionapi.stable_api import IQ_Option
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            client = IQ_Option(email, pwd)
            _configure_proxy(client)
            client.connect()
            connected = bool(client.check_connect())
            if connected:
                iq = client
                IQ_CONNECTED = True
                try:
                    sync_currency_config()
                    iq.change_balance(OTC_MARTI["bal"])
                    bal = float(iq.get_balance() or 0.0)
                    STATS["real_balance"] = bal
                    STATS["balance"] = bal
                except Exception:
                    pass
                return True
        IQ_CONNECTED = False
        return False
    except Exception:
        IQ_CONNECTED = False
        return False


def set_account_balance_mode(bal_type):
    bal_type = "REAL" if str(bal_type).upper() == "REAL" else "PRACTICE"
    OTC_MARTI["bal"] = bal_type
    OTC_MARTI["loss_streak"] = 0
    sync_currency_config()
    if not IQ_CONNECTED and not iq_reconnect():
        return False, 0.0
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(bal_type)
            time.sleep(0.4)
            bal = float(iq.get_balance() or 0.0)
            STATS["real_balance"] = bal
            STATS["balance"] = bal
            return True, bal
    except Exception:
        return False, 0.0


def get_real_balance(bal_type=None):
    target = bal_type or OTC_MARTI["bal"]
    if not IQ_CONNECTED and not iq_reconnect():
        return STATS.get("real_balance", 0.0)
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(target)
            bal = float(iq.get_balance() or 0.0)
            STATS["real_balance"] = bal
            STATS["balance"] = bal
            return bal
    except Exception:
        return STATS.get("real_balance", 0.0)


def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time() - PAYOUT_TIME < 60 and pair in PAYOUT_CACHE:
        return PAYOUT_CACHE[pair]
    if not IQ_CONNECTED and not iq_reconnect():
        return PAYOUT_CACHE.get(pair, 0.85)
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            all_p = iq.get_all_profit()
        if isinstance(all_p, dict) and pair in all_p:
            for k in ["turbo", "blitz", "binary"]:
                if k in all_p[pair]:
                    val = float(all_p[pair][k])
                    if val > 1.0:
                        val = val / 100.0
                    PAYOUT_CACHE[pair] = val
                    PAYOUT_TIME = time.time()
                    return val
        return PAYOUT_CACHE.get(pair, 0.85)
    except Exception:
        return PAYOUT_CACHE.get(pair, 0.85)


def get_candles(pair, size=60, count=100):
    if not IQ_CONNECTED and not iq_reconnect():
        return None
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS:
        return None
    for _ in range(3):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                c = iq.get_candles(pair, size, count, time.time())
            if c and len(c) > 30:
                return pd.DataFrame(sorted(c, key=lambda x: x["from"]))
            time.sleep(0.4)
        except Exception:
            time.sleep(0.4)
    return None


def calc_rsi(closes, period=7):
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def calc_atr(df, period=14):
    try:
        high = df["max"]
        low = df["min"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        val = tr.rolling(period).mean().iloc[-1]
        return float(val) if pd.notna(val) else 0.0005
    except Exception:
        return 0.0005


def calc_adx_v12(df, period=14):
    try:
        high = df["max"]
        low = df["min"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        up = high - high.shift()
        down = low.shift() - low
        plus_dm = ((up > down) & (up > 0)) * up
        minus_dm = ((down > up) & (down > 0)) * down
        plus_di = 100.0 * (plus_dm.rolling(period).mean() / atr.replace(0, 1e-10))
        minus_di = 100.0 * (minus_dm.rolling(period).mean() / atr.replace(0, 1e-10))
        dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10))
        adx = dx.rolling(period).mean().iloc[-1]
        return (
            float(adx) if pd.notna(adx) else 0.0,
            float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else 0.0,
            float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else 0.0,
        )
    except Exception:
        return 0.0, 0.0, 0.0


def get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green):
    trends = []
    trend_score = 0
    e9 = float(close.ewm(9).mean().iloc[-1])
    e21 = float(close.ewm(21).mean().iloc[-1])
    e50 = float(close.ewm(50).mean().iloc[-1])

    if e9 > e21 > e50:
        trends.append("📈 EMA Strong Uptrend")
        trend_score += 2
    elif e9 < e21 < e50:
        trends.append("📉 EMA Strong Downtrend")
        trend_score += 2
    elif e9 > e21:
        trends.append("↗️ EMA Weak Uptrend")
        trend_score += 1
    elif e9 < e21:
        trends.append("↘️ EMA Weak Downtrend")
        trend_score += 1
    else:
        trends.append("➡️ EMA Flat / Ranging")

    if df5 is not None and len(df5) >= 22:
        c5 = df5["close"]
        e9_5 = float(c5.ewm(9).mean().iloc[-1])
        e21_5 = float(c5.ewm(21).mean().iloc[-1])
        if e9_5 > e21_5:
            trends.append("📈 5M Uptrend")
        else:
            trends.append("📉 5M Downtrend")
        if (is_green and e9_5 > e21_5) or (not is_green and e9_5 < e21_5):
            trends.append("✅ 1M + 5M AGREE")
            trend_score += 3
        else:
            trends.append("⚠️ 1M vs 5M CONFLICT")
            trend_score -= 2

    if adx >= 35:
        trends.append(f"💪 ADX Very Strong {adx:.0f}")
        trend_score += 3
    elif adx >= 28:
        trends.append(f"🔥 ADX Strong {adx:.0f}")
        trend_score += 2
    elif adx >= 25:
        trends.append(f"👍 ADX OK {adx:.0f}")
        trend_score += 1
    else:
        trends.append(f"😴 ADX Weak {adx:.0f}")

    if macd_val > sig_val:
        trends.append("📈 MACD Bullish")
        trend_score += 1
    else:
        trends.append("📉 MACD Bearish")
        trend_score += 1

    if mom1 > 0.05:
        trends.append(f"🚀 Momentum +{mom1:.3f}%")
    elif mom1 < -0.05:
        trends.append(f"📉 Momentum {mom1:.3f}%")
    else:
        trends.append(f"🐢 Momentum Slow {mom1:.3f}%")

    if r7 > 70:
        trends.append(f"🔥 RSI Overbought {r7:.0f}")
    elif r7 < 30:
        trends.append(f"❄️ RSI Oversold {r7:.0f}")
    else:
        trends.append(f"✅ RSI Safe {r7:.0f}")

    if c_now > upper:
        trends.append("💥 BB Breakout Up")
    elif c_now < lower:
        trends.append("💥 BB Breakout Down")
    elif upper > lower and (upper - lower) / max(c_now, 1e-10) < 0.0005:
        trends.append("😴 BB Squeeze")
    else:
        trends.append("➡️ BB Inside")

    if trend_score >= 7:
        expiry, expiry_txt, trend_type = 300, "5 Min - STRONG TREND", "🔥 STRONG TREND"
    elif trend_score >= 5:
        expiry, expiry_txt, trend_type = 180, "3 Min - GOOD TREND", "📈 GOOD TREND"
    elif trend_score >= 3:
        expiry, expiry_txt, trend_type = 120, "2 Min - NORMAL TREND", "➡️ NORMAL TREND"
    elif trend_score >= 1:
        expiry, expiry_txt, trend_type = 60, "1 Min - WEAK / RANGING", "😴 WEAK / RANGING"
    else:
        expiry, expiry_txt, trend_type = 60, "1 Min - CONFLICT", "⚠️ CONFLICT TREND"

    return {
        "trends": trends,
        "trend_score": trend_score,
        "expiry": expiry,
        "expiry_txt": expiry_txt,
        "trend_type": trend_type,
    }


def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair, size=60, count=100)
    if df is None or len(df) < 55:
        return None
    try:
        df5 = get_candles(pair, size=300, count=50)
        close = df["close"]
        open_ = df["open"]
        high = df["max"]
        low = df["min"]

        ema9 = close.ewm(9).mean()
        ema21 = close.ewm(21).mean()
        ema50 = close.ewm(50).mean()
        rsi7 = calc_rsi(close, 7)
        rsi14 = calc_rsi(close, 14)
        atr = calc_atr(df, 14)
        adx, pdi, mdi = calc_adx_v12(df)

        ema12 = close.ewm(12).mean()
        ema26 = close.ewm(26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(9).mean()
        macd_val = float(macd.iloc[-1])
        sig_val = float(signal_line.iloc[-1])

        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std().fillna(0.0)
        upper = float((sma20 + 2 * std20).iloc[-1])
        lower = float((sma20 - 2 * std20).iloc[-1])

        low14 = low.rolling(14).min()
        high14 = high.rolling(14).max()
        rng14 = (high14 - low14).replace(0, 1e-10)
        stoch = 100.0 * (close - low14) / rng14
        stoch_val = float(stoch.iloc[-1]) if pd.notna(stoch.iloc[-1]) else 50.0

        c_now = float(close.iloc[-1])
        o_now = float(open_.iloc[-1])
        r7 = float(rsi7.iloc[-1])
        r14 = float(rsi14.iloc[-1])
        mom1 = (float(close.iloc[-1]) - float(close.iloc[-2])) / max(float(close.iloc[-2]), 1e-10) * 100.0
        mom3 = (float(close.iloc[-1]) - float(close.iloc[-4])) / max(float(close.iloc[-4]), 1e-10) * 100.0
        is_green = c_now >= o_now
        payout = get_payout(pair)

        score = 50.0
        reasons = []

        if is_pair_blocked(pair):
            return {
                "pair": pair, "dir": "CALL" if is_green else "PUT", "conf": 0.0,
                "rsi": r7, "adx": adx, "atr": atr, "price": c_now, "payout": payout,
                "expiry": 120, "reason": "Blocked by AI Brain", "trend_info": {}
            }

        bull_pts = 0
        bear_pts = 0
        if float(ema9.iloc[-1]) > float(ema21.iloc[-1]) > float(ema50.iloc[-1]):
            bull_pts += 2
        elif float(ema9.iloc[-1]) < float(ema21.iloc[-1]) < float(ema50.iloc[-1]):
            bear_pts += 2
        if macd_val > sig_val:
            bull_pts += 1
        else:
            bear_pts += 1
        if pdi > mdi:
            bull_pts += 1
        else:
            bear_pts += 1
        if is_green:
            bull_pts += 1
        else:
            bear_pts += 1

        sig = "CALL" if bull_pts >= bear_pts else "PUT"
        aligned_pts = bull_pts if sig == "CALL" else bear_pts
        score += aligned_pts * 5.0
        reasons.append(f"{sig} alignment ({aligned_pts}/5)")

        if adx >= 25:
            score += 8.0
            reasons.append(f"ADX {adx:.0f}")
        else:
            score -= 8.0
            reasons.append(f"Low ADX {adx:.0f}")

        if df5 is not None and len(df5) >= 22:
            c5 = df5["close"]
            up5 = float(c5.ewm(9).mean().iloc[-1]) > float(c5.ewm(21).mean().iloc[-1])
            if (sig == "CALL" and up5) or (sig == "PUT" and not up5):
                score += 8.0
                reasons.append("5M aligned")
            else:
                score -= 10.0
                reasons.append("5M conflict")

        if sig == "CALL" and 45 <= r7 <= 72 and 45 <= r14 <= 70:
            score += 5.0
        elif sig == "PUT" and 28 <= r7 <= 55 and 30 <= r14 <= 55:
            score += 5.0
        elif (sig == "CALL" and r7 > 80) or (sig == "PUT" and r7 < 20):
            score -= 6.0

        if sig == "CALL" and stoch_val < 85:
            score += 3.0
        elif sig == "PUT" and stoch_val > 15:
            score += 3.0

        if payout >= 0.80:
            score += 3.0
        else:
            score -= 10.0
            reasons.append(f"Payout {int(payout * 100)}%")

        s_boost, s_name = get_session_boost(pair)
        score += s_boost
        if s_name:
            reasons.append(s_name)

        pair_s = get_pair_stats(pair)
        score += pair_s.get("score_boost", 0)

        h_boost, h_txt = get_hour_boost(pair)
        score += h_boost
        if h_txt:
            reasons.append(h_txt)

        rsi_boost, rsi_txt = get_pair_rsi_boost(pair, r7)
        score += rsi_boost
        if rsi_txt:
            reasons.append(rsi_txt)

        if sniper_mode:
            score += 2.0

        conf = max(0.0, min(99.0, score))
        trend_info = get_trend_and_expiry(
            df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green
        )

        return {
            "pair": pair,
            "dir": sig,
            "conf": conf,
            "rsi": r7,
            "adx": adx,
            "atr": atr,
            "price": c_now,
            "payout": payout,
            "expiry": trend_info["expiry"],
            "reason": " | ".join(reasons[:4]),
            "trend_info": trend_info,
        }
    except Exception:
        return None


def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 V18 Trailblazer Init...", 0.15),
        (20, f"🔌 Checking {pair}...", 0.2),
        (40, "📊 ADX + ATR + Brain + News + Session...", 0.25),
        (60, "📈 EMA + MACD + 5M Trend...", 0.2),
        (80, "💹 RSI + Stochastic + BB + Multi-Trend...", 0.2),
        (100, "🔒 SNIPER LOCKED!", 0.25),
    ]
    for pct, text, delay in steps:
        filled = int(pct // 5)
        bar = "█" * filled + "░" * (20 - filled)
        color = "🟥" if pct < 40 else "🟨" if pct < 80 else "🟩" if pct < 100 else "💎"
        txt = (
            f"{color} **Z-BOT V18 TRAILBLAZER** {color}\n\n"
            f"💱 {PAIR_EMOJI.get(pair, pair)}\n"
            f"💎 IQ: {'✅' if IQ_CONNECTED else '❌'} ({OTC_MARTI['bal']} {OTC_MARTI['currency']})\n\n"
            f"{bar} {pct}%\n\n🔍 {text}\n⏳ V18"
        )
        try:
            bot.edit_message_text(txt, cid, mid, parse_mode="Markdown")
        except Exception:
            pass
        time.sleep(delay)


def execute_iq_trade(pair, direction, amount, expiry_sec=120):
    if not IQ_CONNECTED and not iq_reconnect():
        return False, None, "IQ Option not connected"
    sync_currency_config()
    bal_mode = "REAL" if is_real_mode() else "PRACTICE"
    expiry_min = max(1, int(round(expiry_sec / 60.0)))
    iq_dir = "call" if str(direction).upper() == "CALL" else "put"
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            iq.change_balance(bal_mode)
            ok, trade_id = iq.buy(float(amount), pair, iq_dir, expiry_min)
            if ok and trade_id:
                STATS["daily_trades"] += 1
        if ok and trade_id:
            return True, trade_id, f"Placed {iq_dir.upper()} {format_money(amount)} ({expiry_min}m) on {bal_mode}"
        return False, None, f"Order rejected by IQ Option ({trade_id})"
    except Exception as e:
        return False, None, f"Trade error: {e}"


def wait_for_iq_result(trade_id, expiry_sec=120):
    if not trade_id or not iq:
        return None
    time.sleep(min(expiry_sec + 5, 310))
    deadline = time.time() + 45
    while time.time() < deadline:
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                if hasattr(iq, "check_win_v4"):
                    res = iq.check_win_v4(trade_id)
                    if res is not None:
                        if isinstance(res, tuple):
                            win_status, profit = res[0], float(res[1] or 0.0)
                            if str(win_status).lower() == "win" or profit > 0:
                                return True
                            if str(win_status).lower() == "loose" or profit < 0:
                                return False
                        elif isinstance(res, (int, float)):
                            if res > 0:
                                return True
                            if res < 0:
                                return False
                if hasattr(iq, "check_win_v3"):
                    profit = iq.check_win_v3(trade_id)
                    if profit is not None and float(profit) != 0.0:
                        return float(profit) > 0
        except Exception:
            pass
        time.sleep(2)
    return None


def check_pullback_ready(pair, orig_dir):
    df = get_candles(pair, size=60, count=60)
    if df is None or len(df) < 25:
        return False, "No candles"
    close = df["close"]
    ema21 = close.ewm(21).mean()
    rsi7 = calc_rsi(close, 7)
    rsi14 = calc_rsi(close, 14)

    c_now = float(close.iloc[-1])
    e21_now = float(ema21.iloc[-1])
    r7_now = float(rsi7.iloc[-1])
    r7_prev = float(rsi7.iloc[-2])
    r14_now = float(rsi14.iloc[-1])
    dist_pct = abs(c_now - e21_now) / max(e21_now, 1e-10) * 100.0

    if orig_dir == "CALL":
        near_ema = dist_pct <= 0.12 and c_now >= e21_now * 0.9992
        rsi_ok = 35 <= r7_now <= 75 and 38 <= r14_now <= 72
        turning = r7_now >= r7_prev - 1.5
        if near_ema and rsi_ok and turning:
            return True, f"Pullback to 21 EMA ({dist_pct:.3f}%), RSI7 {r7_now:.1f}"
    else:
        near_ema = dist_pct <= 0.12 and c_now <= e21_now * 1.0008
        rsi_ok = 25 <= r7_now <= 65 and 28 <= r14_now <= 62
        turning = r7_now <= r7_prev + 1.5
        if near_ema and rsi_ok and turning:
            return True, f"Pullback to 21 EMA ({dist_pct:.3f}%), RSI7 {r7_now:.1f}"

    return False, f"Waiting pullback (dist {dist_pct:.3f}%, RSI7 {r7_now:.1f})"


def pullback_scanner_loop(cid, pair, orig_dir, expiry_sec=120, auto_execute=False):
    sync_currency_config()
    with SESSION_LOCK:
        if SESSION_STATE["in_pullback"] and PULLBACK_STATE.get(cid, {}).get("active"):
            return
        SESSION_STATE["active"] = True
        SESSION_STATE["in_pullback"] = True

    PULLBACK_STATE[cid] = {"active": True, "pair": pair, "dir": orig_dir}
    names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    max_wait_sec = 300
    session_completed = False

    try:
        while PULLBACK_STATE.get(cid, {}).get("active"):
            sync_currency_config()
            idx = OTC_MARTI["loss_streak"]
            if idx <= 0 or idx >= len(OTC_MARTI["levels"]):
                OTC_MARTI["loss_streak"] = 0
                session_completed = True
                break

            stake = get_current_stake()
            lvl_name = names[idx] if idx < len(names) else f"Martingale {idx}"

            if is_news_blocking_pair(pair, minutes=15):
                bot.send_message(cid, f"📰 News near {pair} — pausing pullback scan for 30s.")
                time.sleep(30)
                continue

            ready, info = check_pullback_ready(pair, orig_dir)
            if not ready:
                started_wait = PULLBACK_STATE[cid].get("wait_started") or time.time()
                PULLBACK_STATE[cid]["wait_started"] = started_wait
                if time.time() - started_wait >= max_wait_sec:
                    ready = True
                    info = "Max pullback wait reached — executing level entry"
                else:
                    time.sleep(10)
                    continue

            PULLBACK_STATE[cid]["wait_started"] = None
            entry_dt = get_lagos_now() + timedelta(seconds=10 if auto_execute else 30)
            entry_txt = entry_dt.strftime("%H:%M:%S WAT")

            if CHANNEL_ID:
                send_to_channel_sync(
                    format_channel_pullback_signal(pair, orig_dir, entry_txt, level_idx=idx, amount=stake, expiry=expiry_sec)
                )

            if auto_execute and can_trade_today():
                bot.send_message(
                    cid,
                    f"🔁 **{lvl_name} Pullback Triggered ({pair})**\n📍 {info}\n💵 Placing auto stake **{format_money(stake)}** ({orig_dir})...",
                    parse_mode="Markdown"
                )
                ok, trade_id, msg = execute_iq_trade(pair, orig_dir, stake, expiry_sec=expiry_sec)
                if not ok:
                    bot.send_message(cid, f"⚠️ Auto-trade failed on {lvl_name}: {msg}")
                    time.sleep(15)
                    continue

                won = wait_for_iq_result(trade_id, expiry_sec=expiry_sec)
                if won is True:
                    record_brain(pair, True, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("rsi", 50), ACTIVE_SIGNAL.get("adx", 30))
                    STATS["wins"] += 1
                    OTC_MARTI["loss_streak"] = 0
                    PULLBACK_STATE[cid]["active"] = False
                    session_completed = True
                    bot.send_message(
                        cid,
                        f"✅ **{lvl_name} WON ({format_money(stake)}) on {pair}!**\n♻️ Martingale reset to **{format_money(OTC_MARTI['base'])}**.\n⏳ Resting **3 minutes** before next scan.",
                        parse_mode="Markdown"
                    )
                    return
                else:
                    record_brain(pair, False, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("rsi", 50), ACTIVE_SIGNAL.get("adx", 30))
                    STATS["loss"] += 1
                    OTC_MARTI["loss_streak"] += 1
                    if OTC_MARTI["loss_streak"] >= len(OTC_MARTI["levels"]):
                        OTC_MARTI["loss_streak"] = 0
                        PULLBACK_STATE[cid]["active"] = False
                        session_completed = True
                        max_level_amt = format_money(OTC_MARTI["base"] * OTC_MARTI["levels"][-1])
                        bot.send_message(
                            cid,
                            f"⛔ **Martingale Chain Finished on {pair}**\n❌ Lost up to Level 4 ({max_level_amt}).\n♻️ Reset to **{format_money(OTC_MARTI['base'])}**.\n⏳ Resting **3 minutes** before next scan.",
                            parse_mode="Markdown"
                        )
                        return
                    next_amt = get_current_stake()
                    bot.send_message(
                        cid,
                        f"❌ **{lvl_name} Lost ({format_money(stake)})** — scanning pullback for next stake **{format_money(next_amt)}**...",
                        parse_mode="Markdown"
                    )
                    time.sleep(5)
            else:
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(
                    types.InlineKeyboardButton("✅ WIN - Reset", callback_data=f"manual_win_{pair}"),
                    types.InlineKeyboardButton("❌ LOSS - Next Marti", callback_data=f"manual_loss_{pair}_{orig_dir}"),
                )
                mk.add(types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{pair}"))
                bot.send_message(
                    cid,
                    f"🔁 **{lvl_name} Pullback Ready - {PAIR_EMOJI.get(pair, pair)}**\n"
                    f"📊 {orig_dir} | 💵 Stake: **{format_money(stake)}**\n"
                    f"⏰ Entry: {entry_txt}\n📍 {info}",
                    parse_mode="Markdown",
                    reply_markup=mk
                )
                PULLBACK_STATE[cid]["active"] = False
                set_pullback_active(False)
                return
    finally:
        PULLBACK_STATE[cid] = {"active": False}
        if session_completed:
            finish_trading_session_and_rest(POST_SESSION_REST_SEC)
        else:
            set_pullback_active(False)


def run_auto_otc_trade(cid, pair, dir_, expiry=120, conf=88.0, rsi=50.0, adx=30.0):
    sync_currency_config()
    with SESSION_LOCK:
        if SESSION_STATE["in_pullback"]:
            return
        SESSION_STATE["active"] = True
        SESSION_STATE["rest_until"] = 0.0

    stake = get_current_stake()
    bot.send_message(
        cid,
        f"🤖 **AUTO-TRADE STARTED ({OTC_MARTI['bal']} {OTC_MARTI['currency']})**\n"
        f"💱 {PAIR_EMOJI.get(pair, pair)} | **{dir_}** | 🎯 {conf:.0f}%\n"
        f"💵 Stake: **{format_money(stake)}** | ⏱️ Expiry: {max(1, expiry // 60)}m",
        parse_mode="Markdown"
    )
    ok, trade_id, msg = execute_iq_trade(pair, dir_, stake, expiry_sec=expiry)
    if not ok:
        finish_trading_session_and_rest(POST_SESSION_REST_SEC)
        bot.send_message(cid, f"⚠️ Auto-trade aborted on {pair}: {msg}\n⏳ Resting **3 minutes** before next scan.")
        return
    bot.send_message(cid, f"🚀 {msg} (ID: `{trade_id}`)", parse_mode="Markdown")
    won = wait_for_iq_result(trade_id, expiry_sec=expiry)
    if won is True:
        record_brain(pair, True, conf, rsi, adx)
        STATS["wins"] += 1
        OTC_MARTI["loss_streak"] = 0
        finish_trading_session_and_rest(POST_SESSION_REST_SEC)
        bot.send_message(
            cid,
            f"✅ **AUTO-TRADE WON on {PAIR_EMOJI.get(pair, pair)}!**\n"
            f"💵 Stake: {format_money(stake)} | 🏆 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']}\n"
            f"♻️ Stake reset to **{format_money(OTC_MARTI['base'])}**.\n"
            f"⏳ Resting **3 minutes** before next scan.",
            parse_mode="Markdown"
        )
    else:
        record_brain(pair, False, conf, rsi, adx)
        STATS["loss"] += 1
        OTC_MARTI["loss_streak"] += 1
        if OTC_MARTI["loss_streak"] >= len(OTC_MARTI["levels"]):
            OTC_MARTI["loss_streak"] = 0
            finish_trading_session_and_rest(POST_SESSION_REST_SEC)
            bot.send_message(
                cid,
                f"⛔ **Auto-Trade Martingale Chain Finished on {pair}**\n♻️ Reset stake to **{format_money(OTC_MARTI['base'])}**.\n⏳ Resting **3 minutes** before next scan.",
                parse_mode="Markdown"
            )
            return
        next_amt = get_current_stake()
        bot.send_message(
            cid,
            f"❌ **Auto-Trade Loss on {pair}** — scanning pullback for Martingale **{format_money(next_amt)}**...",
            parse_mode="Markdown"
        )
        pullback_scanner_loop(cid, pair, dir_, expiry_sec=expiry, auto_execute=True)


def handle_new_signal(cid, d, send_channel=True):
    sync_currency_config()
    with SIGNAL_LOCK:
        if not can_start_new_scan_or_signal():
            return False
        pair = d["pair"]
        dir_ = d["dir"]
        conf = d["conf"]
        price = d["price"]
        expiry = d.get("expiry", 120)
        entry_dt = get_lagos_now() + timedelta(seconds=15 if AUTO_TRADE_ENABLED else 45)
        entry_txt = entry_dt.strftime("%H:%M:%S WAT")

        start_signal(
            pair, dir_, conf=conf, rsi=d.get("rsi", 50), adx=d.get("adx", 30),
            price=price, sl=d.get("sl", 0), tp1=d.get("tp1", 0), tp2=d.get("tp2", 0), expiry=expiry
        )

    if send_channel and CHANNEL_ID:
        send_to_channel_sync(format_channel_signal(pair, dir_, conf, price, entry_txt, expiry=expiry))

    stake = get_current_stake()

    if AUTO_TRADE_ENABLED:
        bot.send_message(
            cid,
            f"🤖 **AUTO-TRADE SIGNAL ({OTC_MARTI['bal']} {OTC_MARTI['currency']})**\n"
            f"💱 {PAIR_EMOJI.get(pair, pair)} | **{dir_}** | 🎯 {conf:.0f}%\n"
            f"💵 Stake: **{format_money(stake)}** | ⏱️ Expiry: {max(1, expiry // 60)}m\n"
            f"⏰ Entry: {entry_txt}",
            parse_mode="Markdown"
        )

        def _auto_worker():
            time.sleep(5)
            run_auto_otc_trade(
                cid, pair, dir_, expiry=expiry,
                conf=conf, rsi=d.get("rsi", 50), adx=d.get("adx", 30)
            )

        threading.Thread(target=_auto_worker, daemon=True).start()
        return True

    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("✅ WIN - Reset", callback_data=f"manual_win_{pair}"),
        types.InlineKeyboardButton("❌ LOSS - Pullback Scan", callback_data=f"manual_loss_{pair}_{dir_}"),
    )
    if ENABLE_OTC:
        mk.add(
            types.InlineKeyboardButton("🤖 Auto Trade", callback_data=f"auto_otc_{pair}_{dir_}_{expiry}"),
            types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data=f"skip_{pair}"),
        )
    else:
        mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE", callback_data=f"skip_{pair}"))

    exp_min = max(1, expiry // 60)
    txt = (
        f"📡 **SIGNAL V18 TRAILBLAZER - MANUAL ({OTC_MARTI['bal']} {OTC_MARTI['currency']})** 📡\n\n"
        f"💱 {PAIR_EMOJI.get(pair, pair)}\n"
        f"📊 {'🟢 CALL ⬆️' if dir_ == 'CALL' else '🔴 PUT ⬇️'} | 🎯 {conf:.0f}% SNIPER\n"
        f"📈 {d['reason']} | RSI {d['rsi']:.1f}\n"
        f"💸 {int(d['payout'] * 100)}% | 💰 {price:.5f} | ⏱️ {exp_min} Min\n"
        f"⏰ Entry: {entry_txt}\n"
        f"💵 Stake: {format_money(stake)} (Martingale: {get_martingale_sequence_str()})"
    )
    bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=mk)
    return True


def real_signal_scanner():
    while True:
        try:
            check_and_reset_new_day()
            if is_real_hours() and can_start_new_scan_or_signal():
                best_d = None
                for pair in REAL_PAIRS:
                    if not can_start_new_scan_or_signal():
                        best_d = None
                        break
                    if is_pair_blocked(pair) or is_news_blocking_pair(pair, minutes=30):
                        continue
                    d = analyze_sniper_v12(pair, sniper_mode=True)
                    if d and d["conf"] >= MIN_CONFIDENCE:
                        if not best_d or d["conf"] > best_d["conf"]:
                            best_d = d
                if best_d and can_start_new_scan_or_signal():
                    handle_new_signal(OWNER_ID, best_d, send_channel=True)
        except Exception as e:
            print(f"real_signal_scanner err: {e}")
        time.sleep(25)


def otc_signal_scanner():
    while True:
        try:
            check_and_reset_new_day()
            if ENABLE_OTC and can_start_new_scan_or_signal():
                best_d = None
                for pair in OTC_PAIRS:
                    if not can_start_new_scan_or_signal():
                        best_d = None
                        break
                    if is_pair_blocked(pair):
                        continue
                    d = analyze_sniper_v12(pair, sniper_mode=True)
                    if d and d["conf"] >= MIN_CONFIDENCE:
                        if not best_d or d["conf"] > best_d["conf"]:
                            best_d = d
                if best_d and can_start_new_scan_or_signal():
                    handle_new_signal(OWNER_ID, best_d, send_channel=True)
        except Exception as e:
            print(f"otc_signal_scanner err: {e}")
        time.sleep(30)


def trailblazer_market_scanner():
    global MARKET_GOOD_SENT
    while True:
        try:
            today = get_lagos_day()
            if is_real_hours() and time.time() - MARKET_GOOD_SENT["last_alert"] > 3600:
                good_pairs = []
                for pair in REAL_PAIRS[:8]:
                    if not is_pair_blocked(pair) and not is_news_blocking_pair(pair, minutes=30):
                        d = analyze_sniper_v12(pair, sniper_mode=False)
                        if d and d["conf"] >= 80:
                            good_pairs.append(f"{PAIR_EMOJI.get(pair, pair)} ({d['conf']:.0f}%)")
                if len(good_pairs) >= 3 and CHANNEL_ID:
                    MARKET_GOOD_SENT = {"date": today, "last_alert": time.time()}
                    send_to_channel_sync(
                        "🌊 **MARKET MOMENTUM ALERT** 🌊\n\n"
                        "Strong setups active on:\n• " + "\n• ".join(good_pairs[:5]) + "\n\n📢 @KEVINTRAILBLAZE"
                    )
        except Exception:
            pass
        time.sleep(120)


def morning_greet_loop():
    global MORNING_GREET_SENT
    while True:
        try:
            now = get_lagos_now()
            today = now.strftime("%Y-%m-%d")
            if now.hour == 7 and now.minute < 5 and MORNING_GREET_SENT != today:
                MORNING_GREET_SENT = today
                if CHANNEL_ID:
                    send_to_channel_sync(f"{get_greeting()}\n\n{get_greeting_msg()}\n\n📢 @KEVINTRAILBLAZE")
        except Exception:
            pass
        time.sleep(30)


def daily_summary_loop():
    global DAILY_SUMMARY_SENT
    while True:
        try:
            now = get_lagos_now()
            today = now.strftime("%Y-%m-%d")
            if now.hour == 20 and now.minute < 5 and DAILY_SUMMARY_SENT != today:
                DAILY_SUMMARY_SENT = today
                total = STATS["wins"] + STATS["loss"]
                wr = (STATS["wins"] / total * 100.0) if total else 0.0
                if CHANNEL_ID:
                    send_to_channel_sync(
                        f"📊 **DAILY SESSION SUMMARY ({today})** 📊\n\n"
                        f"🏅 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']}\n"
                        f"📈 Winrate: {wr:.1f}%\n"
                        f"🔢 Trades: {STATS['daily_trades']}/{MAX_DAILY_TRADES}\n\n"
                        f"📢 @KEVINTRAILBLAZE"
                    )
        except Exception:
            pass
        time.sleep(30)


def main_menu_keyboard():
    sync_currency_config()
    mk = types.InlineKeyboardMarkup(row_width=2)
    auto_lbl = "🤖 Auto-Trade: ON" if AUTO_TRADE_ENABLED else "🤖 Auto-Trade: OFF"
    bal_lbl = f"💼 Account: {OTC_MARTI['bal']} ({OTC_MARTI['currency']})"
    otc_lbl = "⚡ OTC: ON" if ENABLE_OTC else "⚡ OTC: OFF"
    mk.add(
        types.InlineKeyboardButton(auto_lbl, callback_data="toggle_auto"),
        types.InlineKeyboardButton(bal_lbl, callback_data="toggle_bal"),
    )
    mk.add(
        types.InlineKeyboardButton("⚡ Scan OTC Pairs", callback_data="scan_all_otc"),
        types.InlineKeyboardButton(otc_lbl, callback_data="toggle_otc"),
    )
    mk.add(
        types.InlineKeyboardButton("📈 Trade Real", callback_data="trade_real"),
        types.InlineKeyboardButton("📊 Scan All Real", callback_data="scan_all_real"),
    )
    mk.add(
        types.InlineKeyboardButton("📉 Stats", callback_data="stats"),
        types.InlineKeyboardButton("🧠 AI Brain", callback_data="brain_btn"),
    )
    mk.add(types.InlineKeyboardButton("⚙️ Settings", callback_data="settings"))
    return mk


@bot.message_handler(commands=["start", "menu"])
def cmd_start(m):
    if not is_allowed(m.from_user.id):
        return
    bot.send_message(
        m.chat.id,
        f"🔥 **TRAILBLAZER V18 CONTROL PANEL**\n📍 `{get_mode_text()}`",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


@bot.message_handler(commands=["practice"])
def cmd_practice(m):
    if not is_allowed(m.from_user.id):
        return
    ok, bal = set_account_balance_mode("PRACTICE")
    bot.send_message(
        m.chat.id,
        f"🎮 **PRACTICE MODE SELECTED (USD)**\nIQ Sync: {'✅' if ok else '⚠️'} | Balance: `{format_money(bal)}`\n💵 Martingale: `{get_martingale_sequence_str()}`",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["real"])
def cmd_real(m):
    if not is_allowed(m.from_user.id):
        return
    ok, bal = set_account_balance_mode("REAL")
    bot.send_message(
        m.chat.id,
        f"💰 **REAL MODE SELECTED (NGN)**\nIQ Sync: {'✅' if ok else '⚠️'} | Balance: `{format_money(bal)}`\n💵 Martingale: `{get_martingale_sequence_str()}`",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["autotrade"])
def cmd_autotrade(m):
    global AUTO_TRADE_ENABLED
    if not is_allowed(m.from_user.id):
        return
    sync_currency_config()
    AUTO_TRADE_ENABLED = True
    bot.send_message(
        m.chat.id,
        f"🤖 **AUTO-TRADE ENABLED**\nAccount: **{OTC_MARTI['bal']} ({OTC_MARTI['currency']})**\nMartingale: `{get_martingale_sequence_str()}`\nTrades & Martingale pullback entries will execute automatically on IQ Option.",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["manual"])
def cmd_manual(m):
    global AUTO_TRADE_ENABLED
    if not is_allowed(m.from_user.id):
        return
    AUTO_TRADE_ENABLED = False
    bot.send_message(
        m.chat.id,
        "✋ **MANUAL SIGNAL MODE ENABLED**\nBot will send signals without auto-placing IQ Option orders.",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["status"])
def cmd_status(m):
    if not is_allowed(m.from_user.id):
        return
    sync_currency_config()
    total = STATS["wins"] + STATS["loss"]
    wr = (STATS["wins"] / total * 100.0) if total else 0.0
    rest_rem = int(get_rest_remaining())
    rest_line = f"\n⏳ Post-Session Rest Remaining: `{rest_rem}s`" if rest_rem > 0 else ""
    bot.send_message(
        m.chat.id,
        f"📊 **STATUS**\n📍 `{get_mode_text()}`\n🏅 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']} ({wr:.1f}%)\n"
        f"🔢 Daily Trades: {STATS['daily_trades']}/{MAX_DAILY_TRADES}\n"
        f"💵 Current Stake: `{format_money(get_current_stake())}` (`{get_martingale_sequence_str()}`)\n"
        f"📉 Martingale Streak: {OTC_MARTI['loss_streak']}/4{rest_line}",
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["brain"])
def cmd_brain(m):
    if not is_allowed(m.from_user.id):
        return
    txt = "🧠 **AI BRAIN V18**\n\n"
    for pair, s in PAIR_BRAIN.items():
        tot = s.get("wins", 0) + s.get("loss", 0)
        if tot > 0:
            wr = s["wins"] / tot * 100.0
            txt += f"• {pair}: W{s['wins']} / L{s['loss']} ({wr:.0f}%)\n"
    if txt == "🧠 **AI BRAIN V18**\n\n":
        txt += "No recorded trades yet."
    bot.send_message(m.chat.id, txt, parse_mode="Markdown")


@bot.message_handler(commands=["welcome"])
def cmd_welcome(m):
    if not is_allowed(m.from_user.id):
        return
    send_photo_to_channel_sync(WELCOME_PHOTO, WELCOME_TEXT)
    bot.reply_to(m, "✅ Welcome message posted to channel.")


@bot.message_handler(commands=["intro"])
def cmd_intro(m):
    if not is_allowed(m.from_user.id):
        return
    send_photo_to_channel_sync(INTRO_PHOTO, INTRO_TEXT)
    bot.reply_to(m, "✅ Intro guide posted to channel.")


@bot.message_handler(commands=["ready"])
def cmd_ready(m):
    if not is_allowed(m.from_user.id):
        return
    send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
    bot.reply_to(m, "✅ Ready checklist posted to channel.")


@bot.callback_query_handler(func=lambda call: True)
def on_callback(c):
    global AUTO_TRADE_ENABLED, ENABLE_OTC
    if not is_allowed(c.from_user.id):
        return
    cid = c.message.chat.id
    data = c.data or ""

    if data == "toggle_auto":
        AUTO_TRADE_ENABLED = not AUTO_TRADE_ENABLED
        bot.answer_callback_query(c.id, f"Auto-Trade: {'ON' if AUTO_TRADE_ENABLED else 'OFF'}")
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=main_menu_keyboard())
        return

    if data == "toggle_otc":
        ENABLE_OTC = not ENABLE_OTC
        bot.answer_callback_query(c.id, f"OTC Mode: {'ON' if ENABLE_OTC else 'OFF'}")
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=main_menu_keyboard())
        return

    if data == "toggle_bal":
        next_bal = "REAL" if OTC_MARTI["bal"] == "PRACTICE" else "PRACTICE"
        ok, bal = set_account_balance_mode(next_bal)
        bot.answer_callback_query(c.id, f"Account: {next_bal} ({OTC_MARTI['currency']})")
        bot.send_message(
            cid,
            f"💼 Switched to **{next_bal} ({OTC_MARTI['currency']})** ({'✅' if ok else '⚠️'} `{format_money(bal)}`)\n"
            f"💵 Martingale: `{get_martingale_sequence_str()}`",
            parse_mode="Markdown"
        )
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=main_menu_keyboard())
        return

    if data.startswith("auto_otc_"):
        with SESSION_LOCK:
            if SESSION_STATE["in_pullback"]:
                bot.answer_callback_query(c.id, "Pullback martingale already running")
                return
        parts = data.replace("auto_otc_", "", 1).split("_")
        pair = parts[0] if len(parts) > 0 else "EURUSD-OTC"
        dir_ = parts[1] if len(parts) > 1 else "CALL"
        expiry = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 120
        AUTO_TRADE_ENABLED = True
        begin_trading_session()
        bot.answer_callback_query(c.id, f"Auto Trading {pair} ({dir_})...")
        threading.Thread(
            target=run_auto_otc_trade,
            args=(cid, pair, dir_, expiry, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("rsi", 50), ACTIVE_SIGNAL.get("adx", 30)),
            daemon=True
        ).start()
        return

    if data == "scan_all_otc":
        if not ENABLE_OTC:
            ENABLE_OTC = True
        if is_signal_active():
            bot.send_message(cid, f"⏳ Signal already active on `{ACTIVE_SIGNAL['pair']}`.", parse_mode="Markdown")
            return
        rest_rem = int(get_rest_remaining())
        if rest_rem > 0:
            bot.send_message(cid, f"⏳ Resting **{rest_rem}s** after previous session before new scans.", parse_mode="Markdown")
            return
        bot.answer_callback_query(c.id, "Scanning OTC pairs...")
        scan_msg = bot.send_message(cid, "⚡ Scanning OTC pairs...")
        results = []
        datas = {}
        for pair in OTC_PAIRS:
            if is_pair_blocked(pair):
                continue
            d = analyze_sniper_v12(pair, sniper_mode=False)
            if d:
                results.append((pair, d["conf"], d["dir"], d["reason"]))
                datas[pair] = d
        results.sort(key=lambda x: x[1], reverse=True)
        lines = [f"⚡ **OTC SCAN ({OTC_MARTI['bal']} {OTC_MARTI['currency']})**\n"]
        for pair, conf, dir_, reason in results[:8]:
            icon = "🟢" if conf >= MIN_CONFIDENCE else "🟡" if conf >= 70 else "🔴"
            lines.append(f"{icon} **{pair}**: {conf:.0f}% {dir_} — {reason}")
        try:
            bot.edit_message_text("\n".join(lines), cid, scan_msg.message_id, parse_mode="Markdown")
        except Exception:
            pass
        if results and results[0][1] >= MIN_CONFIDENCE and can_start_new_scan_or_signal():
            handle_new_signal(cid, datas[results[0][0]], send_channel=False)
        return

    if data.startswith("skip_"):
        pair = data.replace("skip_", "", 1)
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        finish_trading_session_and_rest(SKIP_COOLDOWN)
        bot.answer_callback_query(c.id, "Skipped - Next in 2 min")
        bot.send_message(cid, f"⏭️ **SKIPPED** `{pair}` — no WIN/LOSS recorded.", parse_mode="Markdown")
        return

    if data.startswith("manual_win_"):
        sync_currency_config()
        pair = data.replace("manual_win_", "", 1)
        win_conf = ACTIVE_SIGNAL.get("conf", 88)
        win_rsi = ACTIVE_SIGNAL.get("rsi", 50)
        win_adx = ACTIVE_SIGNAL.get("adx", 30)
        record_brain(pair, True, win_conf, win_rsi, win_adx)
        OTC_MARTI["loss_streak"] = 0
        if cid in PULLBACK_STATE:
            PULLBACK_STATE[cid]["active"] = False
        finish_trading_session_and_rest(POST_SESSION_REST_SEC)
        STATS["wins"] += 1
        count_trade()
        bot.answer_callback_query(c.id, "WIN recorded - 3m rest started")
        bot.send_message(
            cid,
            f"✅ **WIN Recorded on {PAIR_EMOJI.get(pair, pair)}**\n🏅 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']}\n♻️ Stake reset to **{format_money(OTC_MARTI['base'])}**\n⏳ Resting **3 minutes** before next scan.",
            parse_mode="Markdown"
        )
        return

    if data.startswith("manual_loss_"):
        sync_currency_config()
        with SESSION_LOCK:
            if SESSION_STATE["in_pullback"]:
                bot.answer_callback_query(c.id, "Pullback scan already running")
                return
            SESSION_STATE["active"] = True
            SESSION_STATE["in_pullback"] = True
            SESSION_STATE["rest_until"] = 0.0

        parts = data.replace("manual_loss_", "", 1).rsplit("_", 1)
        pair = parts[0]
        orig_dir = parts[1] if len(parts) > 1 else "CALL"
        record_brain(pair, False, ACTIVE_SIGNAL.get("conf", 88), ACTIVE_SIGNAL.get("rsi", 50), ACTIVE_SIGNAL.get("adx", 30))
        OTC_MARTI["loss_streak"] += 1
        STATS["loss"] += 1
        count_trade()
        if OTC_MARTI["loss_streak"] >= len(OTC_MARTI["levels"]):
            OTC_MARTI["loss_streak"] = 0
            if cid in PULLBACK_STATE:
                PULLBACK_STATE[cid]["active"] = False
            finish_trading_session_and_rest(POST_SESSION_REST_SEC)
            bot.answer_callback_query(c.id, "Martingale chain complete - 3m rest")
            bot.send_message(
                cid,
                f"⛔ **CHAIN FINISHED on {pair}**\n♻️ Reset stake to **{format_money(OTC_MARTI['base'])}**.\n⏳ Resting **3 minutes** before next scan.",
                parse_mode="Markdown"
            )
            return
        idx = OTC_MARTI["loss_streak"]
        next_amt = get_current_stake()
        bot.answer_callback_query(c.id, f"LOSS - Scanning pullback for {format_money(next_amt)}")
        bot.send_message(
            cid,
            f"❌ **LOSS Recorded on {pair}**\n🔍 Scanning pullback for Martingale Level {idx + 1}/4 (**{format_money(next_amt)}** {orig_dir})...",
            parse_mode="Markdown"
        )
        threading.Thread(
            target=pullback_scanner_loop,
            args=(cid, pair, orig_dir, ACTIVE_SIGNAL.get("expiry", 120), AUTO_TRADE_ENABLED),
            daemon=True
        ).start()
        return

    if data == "brain_btn":
        cmd_brain(c.message)
        return

    if data == "trade_real":
        mk = types.InlineKeyboardMarkup(row_width=2)
        for p in REAL_PAIRS:
            mk.add(types.InlineKeyboardButton(PAIR_EMOJI.get(p, p), callback_data=f"real_pair_{p}"))
        bot.send_message(cid, "📈 **Select a REAL Forex pair:**", reply_markup=mk, parse_mode="Markdown")
        return

    if data == "scan_all_real":
        if is_signal_active():
            bot.send_message(cid, f"⏳ Signal already active on `{ACTIVE_SIGNAL['pair']}`.", parse_mode="Markdown")
            return
        rest_rem = int(get_rest_remaining())
        if rest_rem > 0:
            bot.send_message(cid, f"⏳ Resting **{rest_rem}s** after previous session before new scans.", parse_mode="Markdown")
            return
        bot.answer_callback_query(c.id, "Scanning REAL pairs...")
        scan_msg = bot.send_message(cid, "🔍 Scanning REAL pairs...")
        results = []
        datas = {}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair) or is_news_blocking_pair(pair, minutes=30):
                continue
            d = analyze_sniper_v12(pair, sniper_mode=False)
            if d:
                results.append((pair, d["conf"], d["dir"], d["reason"]))
                datas[pair] = d
        results.sort(key=lambda x: x[1], reverse=True)
        lines = [f"📊 **REAL SCAN ({OTC_MARTI['bal']} {OTC_MARTI['currency']})**\n"]
        for pair, conf, dir_, reason in results[:8]:
            icon = "🟢" if conf >= MIN_CONFIDENCE else "🟡" if conf >= 70 else "🔴"
            lines.append(f"{icon} **{pair}**: {conf:.0f}% {dir_} — {reason}")
        try:
            bot.edit_message_text("\n".join(lines), cid, scan_msg.message_id, parse_mode="Markdown")
        except Exception:
            pass
        if results and results[0][1] >= MIN_CONFIDENCE and can_start_new_scan_or_signal():
            handle_new_signal(cid, datas[results[0][0]], send_channel=False)
        return

    if data.startswith("real_pair_"):
        pair = data.replace("real_pair_", "", 1)
        if pair not in REAL_PAIRS:
            bot.send_message(cid, f"⚠️ Pair `{pair}` is not enabled.", parse_mode="Markdown")
            return
        if is_pair_blocked(pair):
            bot.send_message(cid, f"🧠 `{pair}` is temporarily blocked by AI Brain.", parse_mode="Markdown")
            return
        nb = is_news_blocking_pair(pair, minutes=30)
        if nb:
            bot.send_message(cid, f"📰 `{pair}` blocked by high-impact news: {nb['title']}", parse_mode="Markdown")
            return
        bot.answer_callback_query(c.id, f"Scanning {pair}...")
        scan_msg = bot.send_message(cid, f"🔍 Scanning {pair}...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d = analyze_sniper_v12(pair, sniper_mode=False)
        if not d or d["conf"] < MIN_CONFIDENCE:
            bot.send_message(
                cid,
                f"⚠️ No 88%+ trade for `{pair}` (Conf: {d['conf'] if d else 0:.0f}% — {d['reason'] if d else 'No data'}).",
                parse_mode="Markdown"
            )
            return
        handle_new_signal(cid, d, send_channel=False)
        return

    if data == "stats":
        cmd_status(c.message)
        return

    if data == "settings":
        sync_currency_config()
        bot.send_message(
            cid,
            f"⚙️ **SETTINGS**\n"
            f"• Mode: `{get_mode_text()}`\n"
            f"• Base Stake: `{format_money(OTC_MARTI['base'])}`\n"
            f"• Martingale: `{get_martingale_sequence_str()}`\n"
            f"• Min Confidence: `{MIN_CONFIDENCE:.0f}%`\n"
            f"• Post-Session Rest: `{POST_SESSION_REST_SEC}s`",
            parse_mode="Markdown"
        )


@app.route("/")
def home():
    return f"V18 TRAILBLAZER RUNNING IQ:{IQ_CONNECTED} AUTO:{AUTO_TRADE_ENABLED} OTC:{ENABLE_OTC} BAL:{OTC_MARTI['bal']}({OTC_MARTI['currency']}) {get_lagos_now().strftime('%H:%M:%S')}"


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def wh():
    if not BOT_TOKEN:
        return "missing token", 500
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok"


if __name__ == "__main__":
    print("Starting Trailblazer IQ Bot...")
    threading.Thread(target=background_iq, daemon=True).start()
    threading.Thread(target=daily_summary_loop, daemon=True).start()
    threading.Thread(target=trailblazer_market_scanner, daemon=True).start()
    threading.Thread(target=morning_greet_loop, daemon=True).start()
    threading.Thread(target=real_signal_scanner, daemon=True).start()
    threading.Thread(target=otc_signal_scanner, daemon=True).start()

    def run_polling():
        while True:
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except Exception as e:
                print(f"Polling error: {e} - Retrying in 5s...")
                time.sleep(5)

    threading.Thread(target=run_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
