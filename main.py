import os, time, threading, warnings, logging, json
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import pytz
import xml.etree.ElementTree as ET
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELE_TOKEN")
OWNER_ID = 8659453018
CHANNEL_ID = "@KEVINTRAILBLAZE"
WELCOME_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
INTRO_PHOTO = "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=1080&q=80"
READY_PHOTO = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=80"
if not BOT_TOKEN: print("ERROR BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
app = Flask(__name__)
ENABLE_OTC = False
REAL_PAIRS = ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD","USDCHF","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","AUDNZD",]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC"]
PAIR_EMOJI = {"EURUSD":"🇪🇺 EUR/USD REAL","GBPUSD":"🇬🇧 GBP/USD REAL","EURGBP":"🇪🇺 EUR/GBP REAL","AUDUSD":"🇦🇺 AUD/USD REAL","USDCAD":"🇺🇸 USD/CAD REAL","USDCHF":"🇺🇸 USD/CHF REAL","EURAUD":"🇪🇺 EUR/AUD REAL","GBPCHF":"🇬🇧 GBP/CHF REAL","EURCHF":"🇪🇺 EUR/CHF REAL","NZDUSD":"🇳🇿 NZD/USD REAL","GBPAUD":"🇬🇧 GBP/AUD REAL","EURCAD":"🇪🇺 EUR/CAD REAL","AUDCAD":"🇦🇺 AUD/CAD REAL","GBPCAD":"🇬🇧 GBP/CAD REAL","AUDNZD":"🇦🇺 AUD/NZD REAL","XAUUSD":"🥇 XAU/USD GOLD","EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC","USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURAUD-OTC":"🇪🇺 EUR/AUD OTC","GBPAUD-OTC":"🇬🇧 GBP/AUD OTC","NZDUSD-OTC":"🇳🇿 NZD/USD OTC","GBPCHF-OTC":"🇬🇧 GBP/CHF OTC","EURCHF-OTC":"🇪🇺 EUR/CHF OTC","USDCAD-OTC":"🇺🇸 USD/CAD OTC","AUDCAD-OTC":"🇦🇺 AUD/CAD OTC","EURCAD-OTC":"🇪🇺 EUR/CAD OTC"}
MARATHON_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","EURJPY-OTC","AUDUSD-OTC","USDZAR-OTC"]
PAIR_EMOJI["USDZAR-OTC"] = "🇿🇦 USD/ZAR OTC"
PAIR_EMOJI["USDJPY-OTC"] = "🇺🇸 USD/JPY OTC"
PAIR_EMOJI["EURJPY-OTC"] = "🇪🇺 EUR/JPY OTC"
# MARATHON - SAFE + SMART COMPOUNDING + CUSTOM TARGET + 1 MIN ONLY
MARATHON = {"active": False, "start": 0.0, "target": 0.0, "bal": 0.0, "wins": 0, "loss": 0, "win_streak": 0, "loss_streak": 0, "cid": None, "bal_type": "PRACTICE", "base_stake": 1.0, "marti_level": 0, "custom_target": False}
MARATHON_PICK = {"pair": None}
MARATHON_TARGET_WAIT = {}
MARATHON_EXPIRY = 1  # 1 MIN ONLY - DO NOT CHANGE
WELCOME_TEXT = "🔥🔥🔥 WELCOME TO TRAILBLAZER SIGNALS 🔥🔥🔥\n━━━━━━━━━━━━━━━━━━\n👋 Welcome Trader! You have arrived at the right place.\n\n🥇 WHAT WE DO HERE\n📈 Forex and GOLD Sniper Signals\n🎯 88%+ Accuracy Only\n🧠 Smart System That Learns From Every Win and Loss\n💰 Martingale 1-2-4-8 To Recover Losses\n\n📜 CHANNEL RULES\n✅ 1. Follow The Stake - $1, $2, $4, $8 - Do Not Be Greedy\n✅ 2. Do Not Overtrade - Maximum 30 Signals Per Day\n✅ 3. Enter Exactly At The Entry Time\n✅ 4. Press WIN or LOSS After Every Trade\n❌ 5. No Spam, No Direct Message To Admin For Signals\n❌ 6. Do Not Borrow Money To Trade\n\n🚀 NEW HERE? Type /intro For A Full Guide\n📊 Type /status To See Today's Result\n📢 Channel: @KEVINTRAILBLAZE\n\n━━━━━━━━━━━━━━━━━━\n💪 Good Luck Trader! Let Us Grow Together! 🤑\n🏆 TRAILBLAZER - WE MOVE! 🔥"
INTRO_TEXT = "📚📚 TRAILBLAZER INTRO 📚📚\n━━━━━━━━━━━━━━━━━━\n💱 WHAT IS FOREX?\nForex Means Foreign Exchange. You Predict If One Currency Will Go UP Or DOWN Against Another.\nExample: EUR/USD - Euro Against Dollar.\nIf Euro Is Strong, Press BUY / CALL\nIf Euro Is Weak, Press SELL / PUT\n\n📈 HOW DO YOU MAKE MONEY?\n1️⃣ Enter With A Stake For Example $1\n2️⃣ If You Are Correct, IQ Option Pays You 85% = $1.85 Back\n3️⃣ If You Are Wrong, We Use Martingale $1 -> $2 -> $4 -> $8 To Recover\n\n🥇 GOLD (XAU/USD) WORKS THE SAME WAY\nGold Price Goes Up And Down. We Trade It With Stop Loss And Take Profit.\n\n🚀 HOW TO START ON IQ OPTION\n1️⃣ CREATE ACCOUNT - Go To iqoption.com\n2️⃣ VERIFY EMAIL\n3️⃣ PRACTICE WITH DEMO - $10,000 DEMO\n4️⃣ VERIFY ACCOUNT (KYC)\n5️⃣ DEPOSIT - Start With $10 To $20 Only\n6️⃣ TRADE WITH US\n\n⚠️ RULES:\n• No Overtrade - Maximum 30 Per Day\n• Follow Stake - $1, $2, $4, $8\n• Trading Has Risk, Only Trade Money You Can Afford To Lose\n\n📢 Channel: @KEVINTRAILBLAZE\n👋 Welcome Again! Let Us Go! 🚀"
STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":""}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0
OTC_SESSION_RESULTS = []
OTC_MARTI = {"loss_streak":0, "base":1.0, "bal":"PRACTICE", "levels":[1,2,4,8]}
PULLBACK_STATE = {}
ACTIVE_SIGNAL = {"active": False, "pair": None, "dir": None, "conf":0, "rsi":0, "adx":0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60}
LAST_GLOBAL_SIGNAL = {"time": 0}
GLOBAL_COOLDOWN = 360
SKIP_COOLDOWN = 120
DAILY_SUMMARY_SENT = ""
MARKET_GOOD_SENT = {"date": "", "last_alert": 0}
MORNING_GREET_SENT = ""
NEWS_CACHE = {"data": [], "time": 0}
def send_to_channel_sync(text):
    try: bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e: print(f"channel send err {e}")
def send_photo_to_channel_sync(photo_url, caption):
    try: bot.send_photo(CHANNEL_ID, photo_url, caption=caption, parse_mode="Markdown")
    except Exception as e:
        print(f"photo channel err {e}")
        try: bot.send_message(CHANNEL_ID, caption, parse_mode="Markdown")
        except: pass
def format_channel_signal(pair, dir_, conf, price, entry_time_txt, expiry=60):
    if dir_ == "CALL":
        action = "🟢 BUY / CALL ⬆️"; meaning = "The Price Is Expected To Go UP, So Press The GREEN BUY / CALL Button In IQ Option"
    else:
        action = "🔴 SELL / PUT ⬇️"; meaning = "The Price Is Expected To Go DOWN, So Press The RED SELL / PUT Button In IQ Option"
    pair_name = PAIR_EMOJI.get(pair, pair)
    price_txt = f"{price:.5f}" if price and price != 0 else "Market Price"
    expiry_min = int(expiry // 60) if expiry else 1
    return f"🔥🔥🔥 TRAILBLAZER SIGNAL 🔥🔥🔥\n\n💱 Pair: {pair_name}\n📊 Signal: {action}\n🎯 Confidence: {conf:.0f}%\n\n💡 What It Means:\n{meaning}\n\n━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: {entry_time_txt}\n💰 ENTRY PRICE: {price_txt}\n💵 STAKE: $1 (If You Lose, Next Is $2, Then $4, Then $8)\n⏱️ EXPIRY: {expiry_min} Minutes\n━━━━━━━━━━━━━━━━━━\n\n👣 HOW TO TRADE:\n1️⃣ Open IQ Option App\n2️⃣ Search For {pair}\n3️⃣ Wait Until {entry_time_txt}\n4️⃣ Set Expiry To {expiry_min} Minutes\n5️⃣ Press {action}\n6️⃣ Enter With $1\n\n📢 Channel: @KEVINTRAILBLAZE\nGood Luck! 💪🤑\n"
def format_channel_gold_signal(d, entry_time_txt):
    dir_e = "🟢 BUY ⬆️" if d['dir']=="CALL" else "🔴 SELL ⬇️"
    what = "The Gold Price Is Expected To Go UP, Press GREEN BUY" if d['dir']=="CALL" else "The Gold Price Is Expected To Go DOWN, Press RED SELL"
    return f"🥇🥇🥇 GOLD SIGNAL - XAU/USD 🥇🥇🥇\n\n📊 Signal: {dir_e}\n🎯 Confidence: {d['conf']:.0f}%\n\n💡 What It Means:\n{what}\n\n━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: {entry_time_txt}\n💰 ENTRY: {d['price']:.2f}\n🛑 STOP LOSS: {d['sl']:.2f}\n🎯 TAKE PROFIT 1: {d['tp1']:.2f}\n🎯 TAKE PROFIT 2: {d['tp2']:.2f}\n━━━━━━━━━━━━━━━━━━\n\n📢 Channel: @KEVINTRAILBLAZE\nLet Us Grow Together! 🔥\n"
def format_channel_pullback_signal(pair, dir_, entry_time_txt, level_idx=1, amount=2.0, expiry=60):
    action = "🟢 BUY / CALL ⬆️" if dir_ == "CALL" else "🔴 SELL / PUT ⬇️"
    pair_name = PAIR_EMOJI.get(pair, pair)
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    level_name = level_names[level_idx] if 1 <= level_idx <= 3 else f"Martingale {level_idx}"
    expiry_min = int(expiry // 60) if expiry else 1
    return f"🔁 {level_name.upper()} - {pair_name}\n\n📊 {action}\n⏰ Entry: {entry_time_txt}\n💵 Stake: ${amount:.2f}\n⏱️ Expiry: {expiry_min} Min\n\n👉 Open IQ Option -> Search {pair} -> Press {action} At Entry Time.\n\n📢 @KEVINTRAILBLAZE\n"
def format_channel_pullback_gold_signal(dir_, entry_time_txt, level_idx=1, amount=2.0):
    dir_e = "🟢 BUY ⬆️" if dir_=="CALL" else "🔴 SELL ⬇️"
    level_names = ["", "Martingale 1", "Martingale 2", "Martingale 3"]
    level_name = level_names[level_idx] if 1 <= level_idx <= 3 else f"Martingale {level_idx}"
    return f"🔁 {level_name.upper()} - 🥇 GOLD XAU/USD\n\n📊 {dir_e}\n⏰ Entry: {entry_time_txt}\n💵 Stake: ${amount:.2f}\n\n👉 Open IQ Option -> Search GOLD -> Press {dir_e} At Entry Time.\nUse Same SL / TP As First Signal.\n\n📢 @KEVINTRAILBLAZE\n"
def get_lagos_day(): return datetime.now(pytz.timezone("Africa/Lagos")).strftime("%Y-%m-%d")
def check_and_reset_new_day():
    today = get_lagos_day()
    if STATS["daily_date"] != today:
        STATS["daily_date"] = today; STATS["daily_trades"] = 0
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60})
        PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    if ACTIVE_SIGNAL["active"] and ACTIVE_SIGNAL.get("day") and ACTIVE_SIGNAL["day"] != today:
        ACTIVE_SIGNAL.update({"active": False, "pair": None, "dir": None, "conf": 0, "rsi": 0, "adx": 0, "started": 0, "day": "", "price": 0, "sl": 0, "tp1": 0, "tp2": 0, "expiry": 60})
        PULLBACK_STATE.clear(); OTC_MARTI["loss_streak"] = 0; return True
    return False
def get_greeting():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "🌅 GOOD MORNING TRAILBLAZER ☀️"
    elif 12 <= hour < 17: return "☀️ GOOD AFTERNOON TRAILBLAZER 🔥"
    elif 17 <= hour < 21: return "🌇 GOOD EVENING TRAILBLAZER 🌙"
    else: return "🌙 GOOD NIGHT TRAILBLAZER 💤"
def get_greeting_msg():
    tz = pytz.timezone("Africa/Lagos"); hour = datetime.now(tz).hour
    if 5 <= hour < 12: return "🌅 Rise And Shine! A New Day, New Money To Earn 💰\n☕ Grab Your Coffee, The Market Is Waking Up!"
    elif 12 <= hour < 17: return "☀️ Afternoon Session! The Market Is Active 🔥\n💪 Stay Focused, Trailblazer!"
    elif 17 <= hour < 21: return "🌇 Evening Session! Last Chance To Earn Before The Market Closes 🌙\n🎯 Let Us Finish Strong!"
    else: return "🌙 The Market Is Resting. Rest Your Mind, Trailblazer 💤\n💰 Tomorrow We Earn Again!"
def get_session_boost(pair):
    tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz); hour = now.hour + now.minute / 60
    if pair=="XAUUSD":
        if 14.5 <= hour < 17: return 10, "🥇🇬🇧🇺🇸 GOLD LONDON+NY OVERLAP 🔥"
        if 8 <= hour < 11: return 8, "🥇 LONDON OPEN GOLD"
        if 12 <= hour < 13.5: return -10, "😴 LUNCH DEAD ZONE"
        if 18 <= hour < 20: return -5, "🌙 EVENING SLOW"
        return 0, "🥇 GOLD NORMAL"
    if 8 <= hour < 11:
        if pair[:3] in ["EUR","GBP","CHF"] or pair[3:6] in ["EUR","GBP","CHF"]: return 8, "🇬🇧 LONDON OPEN"
        return 6, "🇬🇧 LONDON OPEN"
    elif 14.5 <= hour < 17: return 10, "🇬🇧🇺🇸 LONDON + NY OVERLAP 🔥"
    elif 14 <= hour < 14.5: return 4, "🇺🇸 NY PRE-OPEN"
    elif 12 <= hour < 13.5: return -10, "😴 LUNCH DEAD ZONE"
    elif 18 <= hour < 20: return -5, "🌙 EVENING SLOW"
    elif 11 <= hour < 12: return 3, "🇬🇧 LONDON MORNING"
    elif 17 <= hour < 18: return 2, "🇺🇸 NY AFTERNOON"
    else: return 0, "🌍 NORMAL"
def get_upcoming_news():
    try:
        if time.time() - NEWS_CACHE["time"] < 300: return NEWS_CACHE["data"]
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return []
        root = ET.fromstring(r.content)
        now = datetime.now(pytz.timezone("UTC")).replace(tzinfo=None)
        upcoming = []
        for event in root.findall("event"):
            try:
                title = event.find("title").text; country = event.find("country").text; impact = event.find("impact").text
                date_str = event.find("date").text; time_str = event.find("time").text
                if impact != "High": continue
                if country not in ["USD","EUR","GBP","AUD","CAD","NZD","CHF"]: continue
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
                dt_utc = dt + timedelta(hours=5)
                diff_min = (dt_utc - now).total_seconds() / 60
                if -15 <= diff_min <= 120: upcoming.append({"title":title,"country":country,"time_utc":dt_utc,"in_min":int(diff_min),"impact":impact})
            except: continue
        NEWS_CACHE["data"] = upcoming; NEWS_CACHE["time"] = time.time(); return upcoming
    except Exception as e: print(f"News err {e}"); return []
def is_news_blocking_pair(pair, minutes=30):
    news = get_upcoming_news()
    if not news: return None
    if pair=="XAUUSD": base="XAU"; quote="USD"
    else: base = pair[:3]; quote = pair[3:6] if len(pair) >= 6 else ""
    for n in news:
        if n["country"] in [base, quote] and n["in_min"] <= minutes and n["in_min"] >= -15: return n
    return None
def format_news_alert(news_list):
    if not news_list: return ""
    txt = "📰 **UPCOMING HIGH IMPACT NEWS** 📰\n\n"
    for n in news_list:
        flag = {"USD":"🇺🇸","EUR":"🇪🇺","GBP":"🇬🇧","AUD":"🇦🇺","CAD":"🇨🇦","NZD":"🇳🇿","CHF":"🇨🇭"}.get(n["country"], "🌍")
        if n["in_min"] < 0: when = f"Started {-n['in_min']} min ago"
        elif n["in_min"] == 0: when = "⚡ RIGHT NOW!"
        else: when = f"In {n['in_min']} min"
        txt += f"🔴 {flag} {n['country']} - {n['title']}\n⏰ {when}\n\n"
    return txt
def get_ready_text():
    tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
    sb, sn = get_session_boost("EURUSD")
    news = get_upcoming_news()
    news_txt = "✅ No High Impact News In Next 2 Hours - Clean Market" if not news else f"⚠️ {len(news)} High Impact News In Next 2 Hours - Bot Will Avoid Those Pairs"
    return f"🚀🚀🚀 GET READY TRAILBLAZERS 🚀🚀🚀\n\n{get_greeting()}\n\n⏰ Time: {now.strftime('%A, %d %b %Y - %H:%M WAT')}\n⏰ Session: {sn}\n📊 Mode: {get_mode_text()}\n📰 News: {news_txt}\n📅 Today: {STATS['daily_trades']}/30 Trades Used\n\n🔥 SIGNALS ARE COMING SOON - STAY READY! 🔥\n📢 Channel: @KEVINTRAILBLAZE\n"
PAIR_BRAIN = {}
def load_brain():
    global PAIR_BRAIN
    try:
        with open("brain.json","r") as f: PAIR_BRAIN = json.load(f)
    except: PAIR_BRAIN = {}
def save_brain():
    try:
        with open("brain.json","w") as f: json.dump(PAIR_BRAIN, f)
    except: pass
def get_pair_stats(pair):
    if pair not in PAIR_BRAIN: PAIR_BRAIN[pair] = {"wins":0,"loss":0,"history":[],"blocked_until":0,"score_boost":0,"hour_stats":{},"rsi_wins":[],"rsi_loss":[],"best_hour":None,"worst_hour":None,"best_rsi_range":None}
    s = PAIR_BRAIN[pair]
    if "hour_stats" not in s: s["hour_stats"] = {}
    if "rsi_wins" not in s: s["rsi_wins"] = []
    if "rsi_loss" not in s: s["rsi_loss"] = []
    return s
def get_pair_winrate(pair):
    s = get_pair_stats(pair); total = s["wins"] + s["loss"]
    if total < 3: return None
    return s["wins"] / total * 100
def is_pair_blocked(pair):
    s = get_pair_stats(pair); return time.time() < s["blocked_until"]
def record_brain(pair, won, conf, rsi, adx):
    s = get_pair_stats(pair); tz = pytz.timezone("Africa/Lagos"); hour = str(datetime.now(tz).hour)
    if won: s["wins"] += 1
    else: s["loss"] += 1
    if hour not in s["hour_stats"]: s["hour_stats"][hour] = {"wins":0,"loss":0}
    if won: s["hour_stats"][hour]["wins"] += 1
    else: s["hour_stats"][hour]["loss"] += 1
    if won: s["rsi_wins"].append(rsi)
    else: s["rsi_loss"].append(rsi)
    s["rsi_wins"] = s["rsi_wins"][-30:]; s["rsi_loss"] = s["rsi_loss"][-30:]
    s["history"].append({"win":won,"conf":conf,"rsi":rsi,"adx":adx,"time":time.time(),"hour":hour}); s["history"] = s["history"][-30:]
    best_h = None; best_wr = 0; worst_h = None; worst_wr = 100
    for h, st in s["hour_stats"].items():
        total = st["wins"] + st["loss"]
        if total >= 3:
            wr = st["wins"]/total*100
            if wr > best_wr: best_wr = wr; best_h = h
            if wr < worst_wr: worst_wr = wr; worst_h = h
    s["best_hour"] = best_h; s["worst_hour"] = worst_h
    if len(s["rsi_wins"]) >= 5:
        avg_win_rsi = sum(s["rsi_wins"]) / len(s["rsi_wins"]); s["best_rsi_range"] = [avg_win_rsi - 7, avg_win_rsi + 7]
    wr = get_pair_winrate(pair); total = s["wins"] + s["loss"]
    if total >= 5:
        if wr < 40: s["blocked_until"] = time.time() + 7200; s["score_boost"] = -15
        elif wr < 50: s["score_boost"] = -8
        elif wr >= 65: s["score_boost"] = +8; s["blocked_until"] = 0
        elif wr >= 55: s["score_boost"] = +3
        else: s["score_boost"] = 0
    save_brain()
def get_hour_boost(pair):
    s = get_pair_stats(pair); tz = pytz.timezone("Africa/Lagos"); hour = str(datetime.now(tz).hour)
    if hour not in s.get("hour_stats", {}): return 0, ""
    st = s["hour_stats"][hour]; total = st["wins"] + st["loss"]
    if total < 3: return 0, ""
    wr = st["wins"]/total*100
    if wr >= 70: return 8, f"🧠 Best Hour {hour}:00 {wr:.0f}%"
    elif wr >= 60: return 4, f"🧠 Good Hour {hour}:00 {wr:.0f}%"
    elif wr < 40: return -10, f"🧠 Bad Hour {hour}:00 {wr:.0f}%"
    elif wr < 50: return -5, f"🧠 Weak Hour {hour}:00 {wr:.0f}%"
    return 0, ""
def get_pair_rsi_boost(pair, current_rsi, is_call):
    s = get_pair_stats(pair); rng = s.get("best_rsi_range")
    if not rng or len(s.get("rsi_wins", [])) < 5: return 0, ""
    low, high = rng
    if low <= current_rsi <= high: return 6, f"🧠 Pair RSI Sweet Spot {current_rsi:.0f} in [{low:.0f}-{high:.0f}]"
    dist = min(abs(current_rsi - low), abs(current_rsi - high))
    if dist > 15: return -6, f"🧠 Pair RSI Off {current_rsi:.0f} vs Sweet [{low:.0f}-{high:.0f}]"
    return 0, ""
load_brain()
def is_signal_active(): check_and_reset_new_day(); return ACTIVE_SIGNAL["active"]
def start_signal(pair, dir_, conf=0, rsi=0, adx=0, price=0, sl=0, tp1=0, tp2=0, expiry=60):
    check_and_reset_new_day(); ACTIVE_SIGNAL.update({"active":True,"pair":pair,"dir":dir_,"conf":conf,"rsi":rsi,"adx":adx,"started":time.time(),"day":get_lagos_day(),"price":price,"sl":sl,"tp1":tp1,"tp2":tp2,"expiry":expiry})
def clear_signal(): ACTIVE_SIGNAL.update({"active":False,"pair":None,"dir":None,"conf":0,"rsi":0,"adx":0,"started":0,"day":"","price":0,"sl":0,"tp1":0,"tp2":0,"expiry":60})
def is_allowed(uid): return uid == OWNER_ID
def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos"); now = datetime.now(tz)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20
    except:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20
def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC DISABLED - Waiting For REAL 7AM"
def can_trade_today(): check_and_reset_new_day(); return STATS["daily_trades"] < 30
def count_trade(): STATS["daily_trades"] += 1
@app.route("/")
def home(): return f"V18 TRAILBLAZER+XAUUSD RUNNING IQ:{IQ_CONNECTED} MARATHON:{MARATHON['bal_type']} {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S')}"
def background_iq():
    global iq, IQ_CONNECTED
    time.sleep(3)
    for attempt in range(10):
        try:
            from iqoptionapi.stable_api import IQ_Option
            EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS"); PROXY=os.getenv("PROXY_URL")
            if not EMAIL or not PWD: print("IQ_EMAIL/PASS missing"); return
            iq=IQ_Option(EMAIL,PWD)
            if PROXY:
                try:
                    pc = PROXY.replace("http://","").replace("https://","")
                    if "@" in pc:
                        up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
                except: pass
            logging.disable(logging.CRITICAL); iq.connect(); IQ_CONNECTED=iq.check_connect()
            if IQ_CONNECTED:
                try: iq.change_balance("PRACTICE"); time.sleep(1); STATS["real_balance"]=iq.get_balance(); print(f"[IQ] SUCCESS ${STATS['real_balance']}")
                except: pass
                return
            time.sleep(8)
        except Exception as e: print(f"[IQ] Fail {e}"); time.sleep(10)
    IQ_CONNECTED=False
def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL); iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); PROXY=os.getenv("PROXY_URL")
        if PROXY:
            try:
                pc = PROXY.replace("http://","").replace("https://","")
                if "@" in pc:
                    up, hp = pc.split("@"); pu, pp = up.split(":"); ph, pt = hp.split(":"); iq.set_proxy(proxy_type="http", host=ph, port=int(pt), user=pu, password=pp)
            except: pass
        iq.connect(); IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: STATS["real_balance"]=iq.get_balance()
            except: pass
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False
def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK: logging.disable(logging.CRITICAL); iq.change_balance(bal_type); return iq.get_balance()
    except: return 0.0
def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
        if pair in all_p:
            for k in ['blitz','turbo','binary']:
                if k in all_p[pair]: PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(3):
        try:
            logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,100,time.time())
            if c and len(c)>50: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            c2=iq.get_candles(pair,300,50,time.time())
            if c2 and len(c2)>20: return pd.DataFrame(sorted(c2,key=lambda x:x['from']))
            time.sleep(0.4)
        except: time.sleep(0.4)
    return None
def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0); loss=-delta.where(delta<0,0)
    avg_gain=gain.ewm(alpha=1/period, adjust=False).mean(); avg_loss=loss.ewm(alpha=1/period, adjust=False).mean()
    rs=avg_gain/avg_loss; return 100-(100/(1+rs))
def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']; tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs(); tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005
def legit_live_scan(cid, mid, pair):
    steps = [(0,"🚀 V18 Trailblazer Init...",0.15),(20,f"🔌 Checking {pair}...",0.2),(40,"📊 ADX + ATR + Brain + News + Session...",0.25),(60,"📈 EMA + MACD + 5M Trend...",0.2),(80,"💹 RSI + Stochastic + BB + Multi-Trend...",0.2),(100,"🔒 SNIPER LOCKED!",0.3)]
    last_pct=-1
    for pct, text, delay in steps:
        if pct==last_pct: time.sleep(delay); continue
        last_pct=pct; filled=int(pct//5); bar="█"*filled+"░"*(20-filled); color="🟥" if pct<40 else "🟨" if pct<80 else "🟩" if pct<100 else "💎"
        txt=f"{color} **Z-BOT V18 TRAILBLAZER** {color}\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n\n{bar} {pct}%\n\n🔍 {text}\n⏳ V18"
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(delay)
def calc_adx_v12(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']
        tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs()
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); atr=tr.rolling(period).mean()
        up=high-high.shift(); down=low.shift()-low
        plus_dm=((up>down)&(up>0))*up; minus_dm=((down>up)&(down>0))*down
        plus_di=100*(plus_dm.rolling(period).mean()/atr); minus_di=100*(minus_dm.rolling(period).mean()/atr)
        dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di)); adx=dx.rolling(period).mean().iloc[-1]
        return float(adx), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])
    except: return 0, 0, 0
def get_trend_and_expiry(df, df5, close, r7, r14, adx, macd_val, sig_val, mom1, mom3, stoch_val, c_now, upper, lower, is_green):
    trends=[]; trend_score=0
    e9=float(close.ewm(9).mean().iloc[-1]); e21=float(close.ewm(21).mean().iloc[-1]); e50=float(close.ewm(50).mean().iloc[-1])
    if e9>e21>e50: trends.append("📈 EMA Strong Uptrend"); trend_score+=2
    elif e9<e21<e50: trends.append("📉 EMA Strong Downtrend"); trend_score+=2
    elif e9>e21: trends.append("↗️ EMA Weak Uptrend"); trend_score+=1
    elif e9<e21: trends.append("↘️ EMA Weak Downtrend"); trend_score+=1
    else: trends.append("➡️ EMA Flat / Ranging")
    if df5 is not None:
        c5=df5['close']; e9_5=float(c5.ewm(9).mean().iloc[-1]); e21_5=float(c5.ewm(21).mean().iloc[-1])
        if e9_5>e21_5: trends.append("📈 5M Uptrend")
        else: trends.append("📉 5M Downtrend")
        if (is_green and e9_5>e21_5) or (not is_green and e9_5<e21_5): trends.append("✅ 1M + 5M AGREE"); trend_score+=3
        else: trends.append("⚠️ 1M vs 5M CONFLICT"); trend_score-=2
    if adx>=35: trends.append(f"💪 ADX Very Strong {adx:.0f}"); trend_score+=3
    elif adx>=28: trends.append(f"🔥 ADX Strong {adx:.0f}"); trend_score+=2
    elif adx>=25: trends.append(f"👍 ADX OK {adx:.0f}"); trend_score+=1
    else: trends.append(f"😴 ADX Weak {adx:.0f}")
    if macd_val>sig_val: trends.append("📈 MACD Bullish"); trend_score+=1
    else: trends.append("📉 MACD Bearish"); trend_score+=1
    if mom1>0.05: trends.append(f"🚀 Momentum +{mom1:.3f}%")
    elif mom1<-0.05: trends.append(f"📉 Momentum {mom1:.3f}%")
    else: trends.append(f"🐢 Momentum Slow {mom1:.3f}%")
    if r7>70: trends.append(f"🔥 RSI Overbought {r7:.0f}")
    elif r7<30: trends.append(f"❄️ RSI Oversold {r7:.0f}")
    else: trends.append(f"✅ RSI Safe {r7:.0f}")
    if c_now>upper: trends.append("💥 BB Breakout Up")
    elif c_now<lower: trends.append("💥 BB Breakout Down")
    elif (upper-lower)/c_now < 0.0005: trends.append("😴 BB Squeeze")
    else: trends.append("➡️ BB Inside")
    # For normal signals we keep dynamic, but Marathon will force 60s
    if trend_score>=7: expiry=300; expiry_txt="5 Min - STRONG TREND"; trend_type="🔥 STRONG TREND"
    elif trend_score>=5: expiry=180; expiry_txt="3 Min - GOOD TREND"; trend_type="📈 GOOD TREND"
    elif trend_score>=3: expiry=120; expiry_txt="2 Min - NORMAL TREND"; trend_type="➡️ NORMAL TREND"
    elif trend_score>=1: expiry=60; expiry_txt="1 Min - WEAK / RANGING"; trend_type="😴 WEAK / RANGING"
    else: expiry=60; expiry_txt="1 Min - CONFLICT"; trend_type="⚠️ CONFLICT TREND"
    return {"trends":trends,"trend_score":trend_score,"expiry":expiry,"expiry_txt":expiry_txt,"trend_type":trend_type}
def analyze_sniper_v12(pair, sniper_mode=False):
    df = get_candles(pair)
    if df is None: return None
    try:
        df5=None
        try:
            logging.disable(logging.CRITICAL); c5=iq.get_candles(pair,300,50,time.time())
            if c5 and len(c5)>20: df5=pd.DataFrame(sorted(c5,key=lambda x:x['from']))
        except: df5=None
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14); atr=calc_atr(df,14); adx,pdi,mdi=calc_adx_v12(df)
        ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean()
        macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1])
        sma20=close.rolling(20).mean(); std20=close.rolling(20).std(); upper=float((sma20+2*std20).iloc[-1]); lower=float((sma20-2*std20).iloc[-1])
        low14=low.rolling(14).min(); high14=high.rolling(14).max(); stoch=100*(close-low14)/(high14-low14); stoch_val=float(stoch.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now); upper_wick=h_now-max(c_now,o_now); lower_wick=min(c_now,o_now)-l_now; is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if is_pair_blocked(pair): return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"🧠 BRAIN Blocked {pair}","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        news_block=is_news_blocking_pair(pair,minutes=30)
        if news_block: return {"pair":pair,"dir":sig,"conf":40,"price":c_now,"rsi":r7,"reason":f"📰 NEWS BLOCK {news_block['country']} {news_block['title'][:25]} in {news_block['in_min']}min","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if adx<25: return {"pair":pair,"dir":sig,"conf":42,"price":c_now,"rsi":r7,"reason":"Choppy - ADX Low","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if body<atr*0.30: return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":r7,"reason":"Doji - No Body","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if payout<0.80: return {"pair":pair,"dir":sig,"conf":52,"price":c_now,"rsi":r7,"reason":f"Low Payout {int(payout*100)}%","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m=1 if float(e9_5.iloc[-1])>float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"Against 5M Trend - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
            else: score+=12; reasons.append("5M Trend Align")
        else: return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":r7,"reason":"No 5M Data - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        if is_green:
            if e9>e21>e50: score+=18; reasons.append("EMA Bull Align")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=18; reasons.append("EMA Bear Align")
            elif e9<e21: score+=10
            else: score-=8
        if adx>=28: score+=12; reasons.append(f"ADX Strong {adx:.0f}")
        elif adx>=22: score+=7
        if is_green and pdi>mdi: score+=8
        elif not is_green and mdi>pdi: score+=8
        else: score-=10
        if is_green:
            if 52<=r7<=65 and 48<=r14<=62: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7>75 or r7<45: score-=12
            else: score+=6
        else:
            if 35<=r7<=48 and 38<=r14<=52: score+=15; reasons.append(f"RSI Safe {r7:.0f}")
            elif r7<25 or r7>55: score-=12
            else: score+=6
        if is_green and macd_val>sig_val: score+=10; reasons.append("MACD Bull")
        elif not is_green and macd_val<sig_val: score+=10; reasons.append("MACD Bear")
        else: score-=8
        if is_green:
            if mom1>0.03 and mom3>0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1>0.01: score+=5
            elif mom1<0: score-=12
        else:
            if mom1<-0.03 and mom3<-0.06: score+=12; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1<-0.01: score+=5
            elif mom1>0: score-=12
        bull_eng=c_now>o_prev and o_now<c_prev and is_green and c_prev<o_prev; bear_eng=c_now<o_prev and o_now>c_prev and not is_green and c_prev>o_prev
        pin_bull=lower_wick>body*1.8 and lower_wick>upper_wick*1.5 and is_green; pin_bear=upper_wick>body*1.8 and upper_wick>lower_wick*1.5 and not is_green
        has_pattern=False
        if is_green:
            if bull_eng: score+=10; reasons.append("Bull Engulf"); has_pattern=True
            if pin_bull: score+=10; reasons.append("Pin Bull"); has_pattern=True
        else:
            if bear_eng: score+=10; reasons.append("Bear Engulf"); has_pattern=True
            if pin_bear: score+=10; reasons.append("Pin Bear"); has_pattern=True
        if is_green and stoch_val>85: score-=12
        if not is_green and stoch_val<15: score-=12
        if is_green and 50<stoch_val<80: score+=5
        if not is_green and 20<stoch_val<50: score+=5
        if is_green and c_now>upper: score-=10
        if not is_green and c_now<lower: score-=10
        if not has_pattern and score<88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":"No Pattern - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        session_boost,session_name=get_session_boost(pair); score+=session_boost
        if session_boost!=0: reasons.append(f"{session_name} {session_boost:+d}")
        if session_boost<=-10 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"{session_name} - Needs 92% - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        hour_boost,hour_txt=get_hour_boost(pair)
        if hour_boost!=0:
            score+=hour_boost; reasons.append(f"{hour_txt} {hour_boost:+d}")
            if hour_boost<=-10 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"🧠 Bad Hour for {pair} - REJECT","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        rsi_boost,rsi_txt=get_pair_rsi_boost(pair,r7,is_green)
        if rsi_boost!=0: score+=rsi_boost; reasons.append(f"{rsi_txt} {rsi_boost:+d}")
        brain=get_pair_stats(pair); boost=brain.get("score_boost",0); score+=boost
        if boost!=0: reasons.append(f"🧠 Brain {boost:+d}")
        if boost<=-8 and sniper_mode and score<92: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":f"🧠 Weak pair {pair} needs 92%","payout":payout,"expiry":60,"atr":atr,"rejected":True}
        score=max(40,min(96,score)); reason=" + ".join(reasons) if reasons else "Weak PA"
        if sniper_mode and score<88: return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":60,"atr":atr,"rejected":True}
        trend_info=get_trend_and_expiry(df,df5,close,r7,r14,adx,macd_val,sig_val,mom1,mom3,stoch_val,c_now,upper,lower,is_green)
        reason=reason+f" | {trend_info['trend_type']} | ⏱️ 1 Min"
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":r7,"reason":reason,"payout":payout,"expiry":60,"atr":atr,"rejected":False,"adx":adx,"trend_info":trend_info}
    except Exception as e: print(f"V18 err {pair} {e}"); return None
def check_pullback_entry(pair, original_dir):
    if is_news_blocking_pair(pair, minutes=30): return None
    df = get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14)
        r7=float(rsi7.iloc[-1]); r7_prev=float(rsi7.iloc[-2]); r14=float(rsi14.iloc[-1]); c_now=float(close.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); payout=get_payout(pair)
        near_ema=abs(c_now-e9)/c_now*100<0.05 or abs(c_now-e21)/c_now*100<0.05
        if not near_ema or payout<0.80: return None
        if original_dir=="CALL":
            if 40<=r7<=55 and 42<=r14<=58 and r7>r7_prev and c_now>e21: return {"pair":pair,"dir":"CALL","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback CALL | RSI7 {r7:.0f}↑ RSI14 {r14:.0f} at EMA","payout":payout,"expiry":60,"atr":0,"rejected":False}
        else:
            if 45<=r7<=60 and 42<=r14<=58 and r7<r7_prev and c_now<e21: return {"pair":pair,"dir":"PUT","conf":88,"price":c_now,"rsi":r7,"reason":f"Pullback PUT | RSI7 {r7:.0f}↓ RSI14 {r14:.0f} at EMA","payout":payout,"expiry":60,"atr":0,"rejected":False}
        return None
    except: return None
def pullback_scanner_loop(cid, pair, original_dir):
    start=time.time(); PULLBACK_STATE[cid]={"pair":pair,"dir":original_dir,"active":True}
    bot.send_message(cid, f"🔍 **Pullback Scan ON**\n\n💱 {pair} looking for {original_dir} pullback\n📊 Scanning every 10 sec...\n⏳ Timeout 5 min\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP")
    while PULLBACK_STATE.get(cid, {}).get("active") and time.time()-start<300:
        if check_and_reset_new_day(): bot.send_message(cid,"🔄 New day started - Yesterday pullback scan stopped."); PULLBACK_STATE[cid]["active"]=False; return
        if not can_trade_today(): bot.send_message(cid,"⛔ Max 30 trades reached today."); PULLBACK_STATE[cid]["active"]=False; return
        d=check_pullback_entry(pair,original_dir)
        if d:
            levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; amt=OTC_MARTI["base"]*mult; names=["Real Entry","Martingale 1","Martingale 2","Martingale 3"]; dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("❌ LOSS",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_pb_{pair}_{d['dir']}"))
            bot.send_message(cid,f"🎯 **PULLBACK ENTRY FOUND!**\n\n💱 {pair}\n📊 {dir_e} | {d['reason']}\n💸 Payout {int(d['payout']*100)}%\n💰 Next: **{names[idx]} - ${amt:.2f} Level {idx+1}/4 ({mult}x)**\n⏱️ Enter NOW - 1 Min - MANUAL\n\nPress WIN/LOSS/SKIP after result:",reply_markup=mk,parse_mode="Markdown")
            PULLBACK_STATE[cid]["active"]=False; return
        time.sleep(10)
    PULLBACK_STATE[cid]={"active":False}; bot.send_message(cid,"⏱️ Pullback scan timeout (5 min) - No safe entry.")
def daily_summary_loop():
    global DAILY_SUMMARY_SENT
    tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            now=datetime.now(tz); today_str=now.strftime("%Y-%m-%d")
            if now.hour==20 and now.minute<5 and DAILY_SUMMARY_SENT!=today_str:
                DAILY_SUMMARY_SENT=today_str; total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
                best_pair=""; best_wr=0; bad_pair=""; bad_wr=100
                for pair,s in PAIR_BRAIN.items():
                    t=s["wins"]+s["loss"]
                    if t>=3:
                        w=s["wins"]/t*100
                        if w>best_wr: best_wr=w; best_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                        if w<bad_wr: bad_wr=w; bad_pair=f"{pair} {w:.0f}% (W{s['wins']} L{s['loss']})"
                msg=f"📊 **DAILY SUMMARY - {today_str}** 📊\n\n🕗 Trading closed for today (8PM)\n\n🏆 Wins: {STATS['wins']}\n❌ Losses: {STATS['loss']}\n📈 Win Rate: {wr:.1f}%\n📅 Total Trades Today: {STATS['daily_trades']}/30\n\n🏆 **Best Pair:** {best_pair if best_pair else 'Not enough data yet'}\n💀 **Worst Pair:** {bad_pair if bad_pair else 'None - all good'}\n\n🧠 Brain has learned from {len(PAIR_BRAIN)} pairs.\n\n🌙 {get_greeting()} - Rest well Trailblazer! 💰\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def trailblazer_market_scanner():
    tz=pytz.timezone("Africa/Lagos"); last_news_alert=0
    while True:
        try:
            if MARATHON["active"]: time.sleep(60); continue
            if not is_real_hours() or not IQ_CONNECTED: time.sleep(60); continue
            news=get_upcoming_news(); urgent_news=[n for n in news if 0<=n["in_min"]<=30]
            if urgent_news and time.time()-last_news_alert>3600:
                last_news_alert=time.time(); news_txt=format_news_alert(urgent_news)
                msg=f"📰📰📰 **TRAILBLAZER NEWS ALERT** 📰📰📰\n\n{get_greeting()}\n\n⚠️ **HIGH IMPACT NEWS COMING!** ⚠️\n\n{news_txt}\n🚨 Do not trade pairs with that currency now\n⏳ Wait 15 min AFTER news\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            if time.time()-MARKET_GOOD_SENT["last_alert"]<2700: time.sleep(60); continue
            if is_signal_active(): time.sleep(60); continue
            good_pairs=0; strong_pairs=[]
            for pair in ["EURUSD","GBPUSD","EURGBP","AUDUSD","USDCAD"]:
                if is_pair_blocked(pair): continue
                if is_news_blocking_pair(pair,minutes=30): continue
                try:
                    df=get_candles(pair)
                    if df is None: continue
                    adx,_,_=calc_adx_v12(df); payout=get_payout(pair)
                    if adx>=25 and payout>=0.80: good_pairs+=1; strong_pairs.append(pair)
                except: pass
                time.sleep(1)
            if urgent_news and good_pairs<5: time.sleep(300); continue
            if good_pairs>=5:
                MARKET_GOOD_SENT["last_alert"]=time.time(); greet=get_greeting(); pairs_txt=" • ".join(strong_pairs[:5])
                if news: news_note=f"\n📰 **News Note:** {len(news)} high impact news in next 2h - Bot is avoiding news pairs ✅\n"
                else: news_note="\n📰 **News:** ✅ No high impact news in next 2h - Clean market! ✅\n"
                session_boost,session_name=get_session_boost("EURUSD")
                msg=f"🔥🔥🔥 **TRAILBLAZER MARKET IS GOOD** 🔥🔥🔥\n\n{greet}\n\n🚀 **SIGNALS COMING SOON - GET READY** 💰💰💰\n\n📊 Market Check:\n✅ {good_pairs}/5 Major Pairs Strong Trend\n✅ ADX 25+ - Market is moving\n✅ Payout 80%+\n💱 Hot Pairs: {pairs_txt}\n⏰ Session: {session_name}\n{news_note}\n⏰ Time: {datetime.now(tz).strftime('%H:%M WAT')}\n🎯 Bot is scanning now... 88%+ signals only!\n\n💪 Get your IQ Option ready!\n💰 **IT IS TIME TO EARN!** 🚀🚀🚀\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            time.sleep(300)
        except: time.sleep(60)
def morning_greet_loop():
    global MORNING_GREET_SENT
    tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            now=datetime.now(tz); today=now.strftime("%Y-%m-%d")
            if now.hour==7 and now.minute<5 and MORNING_GREET_SENT!=today:
                MORNING_GREET_SENT=today
                msg="🌅🌅🌅 **GOOD MORNING TRAILBLAZER** 🌅🌅🌅\n\n☀️ Rise and shine! It is 7AM - Market just opened!\n\n💰 **New day, new money to earn!** 💰\n\n📊 **Today's Plan:**\n✅ Bot is now scanning 15 REAL pairs + XAUUSD GOLD\n✅ Only 88%+ SNIPER signals\n✅ Max 30 trades\n🧠 Brain is ready\n⏭️ SKIP button\n📰 News scanner ON\n⏰ Session boost ON\n\n🔥 **LET US EARN TODAY!** 🚀💰🔥\n"
                try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown")
                except: pass
            time.sleep(60)
        except: time.sleep(60)
def analyze_xauusd():
    pair="XAUUSD"; df=get_candles(pair)
    if df is None: return None
    try:
        df5=None
        try:
            logging.disable(logging.CRITICAL); c5=iq.get_candles(pair,300,50,time.time())
            if c5 and len(c5)>20: df5=pd.DataFrame(sorted(c5,key=lambda x:x['from']))
        except: df5=None
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi7=calc_rsi(close,7); rsi14=calc_rsi(close,14); atr=calc_atr(df,14); adx,pdi,mdi=calc_adx_v12(df)
        ema12=close.ewm(12).mean(); ema26=close.ewm(26).mean(); macd=ema12-ema26; signal=macd.ewm(9).mean()
        macd_val=float(macd.iloc[-1]); sig_val=float(signal.iloc[-1])
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        r7=float(rsi7.iloc[-1]); r14=float(rsi14.iloc[-1]); mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        is_green=c_now>o_now; payout=get_payout(pair); sig="CALL" if is_green else "PUT"
        if is_pair_blocked(pair): return None
        if is_news_blocking_pair(pair,minutes=30): return None
        if adx<25: return None
        if payout<0.80: return None
        score=30; reasons=[]
        if df5 is not None:
            c5=df5['close']; e9_5=c5.ewm(9).mean(); e21_5=c5.ewm(21).mean(); trend_5m=1 if float(e9_5.iloc[-1])>float(e21_5.iloc[-1]) else -1
            if (is_green and trend_5m==-1) or (not is_green and trend_5m==1): return None
            else: score+=12; reasons.append("5M Align")
        else: return None
        if is_green:
            if e9>e21>e50: score+=18; reasons.append("EMA Bull")
            elif e9>e21: score+=10
            else: score-=8
        else:
            if e9<e21<e50: score+=18; reasons.append("EMA Bear")
            elif e9<e21: score+=10
            else: score-=8
        if adx>=28: score+=12; reasons.append(f"ADX {adx:.0f}")
        elif adx>=22: score+=7
        if is_green and pdi>mdi: score+=8
        elif not is_green and mdi>pdi: score+=8
        else: score-=10
        if is_green:
            if 52<=r7<=65: score+=15; reasons.append(f"RSI {r7:.0f}")
            elif r7>75 or r7<45: score-=12
            else: score+=6
        else:
            if 35<=r7<=48: score+=15; reasons.append(f"RSI {r7:.0f}")
            elif r7<25 or r7>55: score-=12
            else: score+=6
        if is_green and macd_val>sig_val: score+=10; reasons.append("MACD Bull")
        elif not is_green and macd_val<sig_val: score+=10; reasons.append("MACD Bear")
        else: score-=8
        if is_green and mom1>0.03: score+=12
        elif not is_green and mom1<-0.03: score+=12
        elif (is_green and mom1<0) or (not is_green and mom1>0): score-=12
        session_boost,session_name=get_session_boost(pair); score+=session_boost
        hour_boost,_=get_hour_boost(pair); score+=hour_boost
        brain=get_pair_stats(pair); score+=brain.get("score_boost",0)
        score=max(40,min(96,score))
        if score<88: return None
        entry=c_now; sl_dist=float(atr)*1.5
        if sig=="CALL": sl=entry-sl_dist; tp1=entry+sl_dist; tp2=entry+(sl_dist*2)
        else: sl=entry+sl_dist; tp1=entry-sl_dist; tp2=entry-(sl_dist*2)
        return {"pair":pair,"dir":sig,"conf":score,"price":entry,"rsi":r7,"reason":" + ".join(reasons),"payout":payout,"atr":float(atr),"adx":adx,"sl":sl,"tp1":tp1,"tp2":tp2,"session":session_name}
    except Exception as e: print(f"XAU err {e}"); return None
def xauusd_signal_scanner():
    tz=pytz.timezone("Africa/Lagos"); last_xau=0
    while True:
        try:
            check_and_reset_new_day()
            if MARATHON["active"]: time.sleep(30); continue
            if is_signal_active(): time.sleep(15); continue
            if time.time()-LAST_GLOBAL_SIGNAL["time"]<GLOBAL_COOLDOWN: time.sleep(30); continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today(): time.sleep(60); continue
                if time.time()-last_xau<600: time.sleep(30); continue
                d=analyze_xauusd()
                if d:
                    now=datetime.now(tz); entry_time=now+timedelta(seconds=45); dir_e="🟢 BUY ⬆️" if d['dir']=="CALL" else "🔴 SELL ⬇️"; base=OTC_MARTI["base"]
                    mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_XAUUSD"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_XAUUSD_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_XAUUSD")); mk.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_XAUUSD_{d['dir']}"))
                    msg=f"🥇🥇🥇 **XAU/USD GOLD SIGNAL** 🥇🥇🥇\n\n{dir_e} | 🎯 {d['conf']:.0f}% SNIPER GOLD\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.2f}\n⏰ Session: {d['session']}\n📰 News: ✅ Checked\n📅 Today: {STATS['daily_trades']}/30\n\n━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: {entry_time.strftime('%H:%M:%S WAT')}\n💰 ENTRY: {d['price']:.2f}\n🛑 SL: {d['sl']:.2f}\n🎯 TP1: {d['tp1']:.2f} (1:1 Secure)\n🎯 TP2: {d['tp2']:.2f} (1:2 Runner)\n━━━━━━━━━━━━━━━━━━\n\n💵 **Stake:** ${base:.2f}\n**Marti 1:** ${base*2:.2f} | **Marti 2:** ${base*4:.2f} | **Marti 3:** ${base*8:.2f}\n💸 Payout: {int(d['payout']*100)}%\n\n⚠️ MANUAL - Enter At ENTRY TIME\nPress WIN / LOSS / SKIP\n"
                    bot.send_message(OWNER_ID,msg,parse_mode="Markdown",reply_markup=mk); last_xau=time.time(); LAST_GLOBAL_SIGNAL["time"]=time.time(); start_signal("XAUUSD",d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], sl=d['sl'], tp1=d['tp1'], tp2=d['tp2'])
            time.sleep(25)
        except: time.sleep(30)
def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            check_and_reset_new_day()
            if MARATHON["active"]: time.sleep(30); continue
            if is_signal_active(): time.sleep(15); continue
            if time.time()-LAST_GLOBAL_SIGNAL["time"]<GLOBAL_COOLDOWN: time.sleep(30); continue
            if is_real_hours() and IQ_CONNECTED:
                if not can_trade_today(): time.sleep(60); continue
                candidates=[]
                for pair in REAL_PAIRS:
                    if is_pair_blocked(pair): continue
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_sniper_v12(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=88: candidates.append((pair,d))
                    time.sleep(3)
                if candidates:
                    candidates.sort(key=lambda x:x[1]['conf'],reverse=True); pair,d=candidates[0]; now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
                    mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_{pair}_{d['dir']}"))
                    wr=get_pair_winrate(pair); wr_txt=f" | 🧠 Brain WR {wr:.0f}%" if wr is not None else ""; ti=d.get('trend_info',{}); expiry_min=1; trend_type_txt=ti.get('trend_type','➡️ NORMAL TREND'); trends_txt=" | ".join(ti.get('trends',[])[:4])
                    msg=f"📡 **REAL SIGNAL V18 TRAILBLAZER - MANUAL** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER{wr_txt}\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n📊 Trend: {trend_type_txt}\n🔍 Trends: {trends_txt}\n💸 {int(d['payout']*100)}% | ⏱️ Suggested: {expiry_min} Min\n📅 Today: {STATS['daily_trades']}/30\n📰 News: ✅ Checked - No blocking news\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Real Entry:** ${base:.2f}\n**If LOSS ->** Martingale 1: ${base*2:.2f}\n**If LOSS ->** Martingale 2: ${base*4:.2f}\n**If LOSS ->** Martingale 3: ${base*8:.2f}\n\n⚠️ MANUAL - Press WIN / LOSS / SKIP\n"
                    try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown",reply_markup=mk); last_signal[pair]=time.time(); LAST_GLOBAL_SIGNAL["time"]=time.time(); start_signal(pair,d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], expiry=60)
                    except Exception as e: print(f"Send err {e}")
            time.sleep(25)
        except: time.sleep(30)
# ========== MARATHON - SAFE + SMART COMPOUNDING + CUSTOM TARGET + 1 MIN ONLY ==========
def marathon_stake():
    bal = MARATHON["bal"]; start = MARATHON["start"]; target = MARATHON["target"]
    progress = 0
    if target > start:
        progress = (bal - start) / (target - start)
        progress = max(0, min(1, progress))
    if progress < 0.25: pct = 0.10
    elif progress < 0.50: pct = 0.12
    elif progress < 0.75: pct = 0.13
    else: pct = 0.14
    if MARATHON["loss_streak"] >= 2: pct = 0.05
    stake = round(bal * pct, 2)
    stake = max(1.0, min(5.0, stake))
    max_stake = round(bal * 0.15, 2)
    if stake > max_stake: stake = max(1.0, max_stake)
    MARATHON["base_stake"] = stake
    return stake
def analyze_marathon_30s(pair):
    df = get_candles(pair)
    if df is None: return None
    try:
        close = df['close']
        e9 = float(close.ewm(9).mean().iloc[-1]); e21 = float(close.ewm(21).mean().iloc[-1])
        r7 = float(calc_rsi(close,7).iloc[-1])
        mom1 = (close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3 = (close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        c_now = float(close.iloc[-1]); o_now = float(df['open'].iloc[-1])
        is_green = c_now > o_now
        payout = get_payout(pair)
        if payout < 0.80: return None
        if is_green:
            if not (e9 > e21): return None
            if not (50 <= r7 <= 72): return None
            if not (mom1 > 0.01 and mom3 > 0): return None
            return {"pair":pair,"dir":"CALL","conf":80,"price":c_now,"rsi":r7,"payout":payout}
        else:
            if not (e9 < e21): return None
            if not (28 <= r7 <= 50): return None
            if not (mom1 < -0.01 and mom3 < 0): return None
            return {"pair":pair,"dir":"PUT","conf":80,"price":c_now,"rsi":r7,"payout":payout}
    except: return None
def marathon_auto_buy(pair, amount, direction):
    # 1 MIN ONLY
    for attempt in range(3):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                iq.change_balance(MARATHON["bal_type"])
                time.sleep(0.5)
                bal = iq.get_balance()
                print(f"[MARATHON BUY TRY {attempt+1}] Bal ${bal} | {pair} {direction} ${amount} | 1 MIN | Type {MARATHON['bal_type']}")
                if bal < amount:
                    print(f"[MARATHON BUY FAIL] Low balance ${bal} < ${amount}")
                    return False, None
                status, trade_id = iq.buy(amount, pair, direction.lower(), 1)  # 1 = 1 MIN
                print(f"[MARATHON AUTO {MARATHON['bal_type']}] {pair} {direction} ${amount} 1MIN -> {status} {trade_id}")
                if status: return True, trade_id
                print(f"[MARATHON BUY REJECTED] Attempt {attempt+1} - IQ said False, retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"[MARATHON AUTO ERR {attempt+1}] {e}")
            try: iq_reconnect(); time.sleep(2)
            except: pass
    return False, None
def marathon_check_win(trade_id):
    try:
        print(f"[MARATHON CHECK] Waiting for trade {trade_id} to close - 1 MIN...")
        for i in range(13):
            time.sleep(5)
            if not MARATHON["active"]: return None, 0
            if i >= 11:
                try:
                    with IQ_LOCK:
                        logging.disable(logging.CRITICAL)
                        win, profit = iq.check_win_v2(trade_id)
                        print(f"[MARATHON CHECK TRY {i}] win={win} profit={profit}")
                        if win is not None: return win, profit
                except Exception as e: print(f"[MARATHON CHECK ERR TRY {i}] {e}"); time.sleep(2)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                info = iq.get_optioninfo_v2(trade_id)
                print(f"[MARATHON CHECK INFO] {info}")
                if info and 'win' in info:
                    win = info['win']; profit = float(info.get('profit', 0))
                    if win is not None: return win, profit
        except Exception as e: print(f"[MARATHON CHECK INFO ERR] {e}")
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                iq.change_balance(MARATHON["bal_type"])
                new_bal = iq.get_balance()
                print(f"[MARATHON CHECK BAL] Old {MARATHON['bal']:.2f} New {new_bal:.2f}")
                if new_bal > MARATHON["bal"]: return True, round(new_bal - MARATHON["bal"], 2)
                elif new_bal < MARATHON["bal"]: return False, 0
        except Exception as e: print(f"[MARATHON CHECK BAL ERR] {e}")
        return None, 0
    except Exception as e: print(f"[MARATHON CHECK ERR] {e}"); return None, 0
def marathon_scan_all_text():
    if not IQ_CONNECTED: return "⏳ IQ not connected yet - wait 30s and try again", []
    txt = "📊 **MARATHON SCAN ALL - 6 PAIRS - 1 MIN ONLY**\n"
    txt += f"💰 Mode: {MARATHON['bal_type']} | Payout 80%+ | Expiry 1 Min\n\n"
    results = []
    for pair in MARATHON_PAIRS:
        try:
            d = analyze_marathon_30s(pair)
            if d:
                results.append(d)
                txt += f"🟢 {PAIR_EMOJI.get(pair,pair)}: {d['dir']} | RSI {d['rsi']:.0f} | Payout {int(d['payout']*100)}% - READY\n"
            else:
                txt += f"🔴 {PAIR_EMOJI.get(pair,pair)}: No edge / Payout <80% - SKIP\n"
        except: txt += f"🔴 {pair}: Error\n"
        time.sleep(0.5)
    if results: txt += f"\n💡 BEST: {results[0]['pair']} {results[0]['dir']}"
    else: txt += "\n⏳ No clean setup now, try again in 1 min..."
    return txt, results
def marathon_loop():
    last_trade_time = 0
    while MARATHON["active"]:
        try:
            if time.time() - last_trade_time < 90:
                time.sleep(5); continue
            if not IQ_CONNECTED:
                bot.send_message(MARATHON["cid"], "⏳ Waiting for IQ to connect... Marathon paused 10s")
                time.sleep(10); continue
            if MARATHON["bal"] >= MARATHON["target"]:
                bot.send_message(MARATHON["cid"], f"🏁 **MARATHON DONE! [{MARATHON['bal_type']}]**\n\n💰 Start: ${MARATHON['start']:.2f}\n🏆 Now: ${MARATHON['bal']:.2f}\n🎯 Target: ${MARATHON['target']:.2f} REACHED!\n✅ AUTO STOPPED\n\nW:{MARATHON['wins']} L:{MARATHON['loss']}")
                MARATHON["active"] = False; clear_signal(); break
            # STOP LOSS 30% - Protect, no chop full money
            stop_loss = MARATHON["start"] * 0.70
            if MARATHON["bal"] <= stop_loss:
                bot.send_message(MARATHON["cid"], f"🛑 **MARATHON STOPPED - STOP LOSS HIT [{MARATHON['bal_type']}]**\n\n💰 Start: ${MARATHON['start']:.2f}\n📉 Now: ${MARATHON['bal']:.2f}\n🛡️ Lost 30% - I stop to protect your remaining money\nW:{MARATHON['wins']} L:{MARATHON['loss']}\n\nYou still get ${MARATHON['bal']:.2f} remain, no be $0")
                MARATHON["active"] = False; break
            if MARATHON["bal"] <= 1:
                bot.send_message(MARATHON["cid"], f"🛑 **MARATHON STOPPED - BALANCE LOW [{MARATHON['bal_type']}]**\nBal: ${MARATHON['bal']:.2f}")
                MARATHON["active"] = False; break
            found = None
            if MARATHON_PICK["pair"]:
                found = analyze_marathon_30s(MARATHON_PICK["pair"])
                if not found:
                    time.sleep(10); continue
            else:
                for pair in MARATHON_PAIRS:
                    if not MARATHON["active"]: break
                    d = analyze_marathon_30s(pair)
                    if d: found = d; break
                    time.sleep(2)
                if not found:
                    time.sleep(15); continue
            stake = marathon_stake()
            dir_e = "🟢 CALL ⬆️" if found['dir']=="CALL" else "🔴 PUT ⬇️"
            progress_pct = int((MARATHON['bal'] - MARATHON['start']) / (MARATHON['target'] - MARATHON['start']) * 100) if MARATHON['target'] > MARATHON['start'] else 0
            progress_pct = max(0, min(100, progress_pct))
            bot.send_message(MARATHON["cid"], f"🏁 **MARATHON AUTO-PLACING... [{MARATHON['bal_type']}]**\n\n💱 {PAIR_EMOJI.get(found['pair'],found['pair'])}\n📊 {dir_e} | RSI {found['rsi']:.0f} | Payout {int(found['payout']*100)}%\n💰 Stake: ${stake:.2f} (Smart Compounding {progress_pct}%) | Bal: ${MARATHON['bal']:.2f} / Target ${MARATHON['target']:.2f}\n⏱️ Expiry: 1 MIN ONLY\n🤖 Placing on IQ {MARATHON['bal_type']} now...")
            start_signal(found['pair'], found['dir'], found['conf'], found['rsi'], 30, price=found['price'], expiry=60)
            status, trade_id = marathon_auto_buy(found['pair'], stake, found['dir'])
            if not status:
                bot.send_message(MARATHON["cid"], f"❌ **AUTO PLACE FAILED [{MARATHON['bal_type']}]**\n\n💱 {found['pair']} - IQ rejected / No connection\nRetrying in 15s...")
                clear_signal(); time.sleep(15); continue
            last_trade_time = time.time()
            bot.send_message(MARATHON["cid"], f"✅ **TRADE PLACED [{MARATHON['bal_type']}]** ID: {trade_id}\n⏱️ Expiry: 1 MIN | Waiting for result... ⏳")
            win, profit = marathon_check_win(trade_id)
            clear_signal()
            last_trade_time = time.time()
            if win is None:
                bot.send_message(MARATHON["cid"], "⚠️ Could not confirm result, resting 30s...")
                time.sleep(30); continue
            if win:
                MARATHON["bal"] += float(profit); MARATHON["wins"]+=1; MARATHON["win_streak"]+=1; MARATHON["loss_streak"]=0; MARATHON["marti_level"]=0
                record_brain(found['pair'], True, 80, found['rsi'], 30)
                progress2 = int((MARATHON['bal'] - MARATHON['start']) / (MARATHON['target'] - MARATHON['start']) * 100) if MARATHON['target'] > MARATHON['start'] else 0
                progress2 = max(0, min(100, progress2))
                bot.send_message(MARATHON["cid"], f"✅ **MARATHON WIN [{MARATHON['bal_type']}]** +${float(profit):.2f}\nBal: ${MARATHON['bal']:.2f} / Target ${MARATHON['target']:.2f}\n📈 Progress: {progress2}% | Next Stake: ${marathon_stake():.2f} (Compounding)\n⏱️ Expiry was 1 MIN\n⏳ Resting 90s...")
            else:
                MARATHON["bal"] -= stake; MARATHON["loss"]+=1; MARATHON["loss_streak"]+=1; MARATHON["win_streak"]=0
                record_brain(found['pair'], False, 80, found['rsi'], 30)
                bot.send_message(MARATHON["cid"], f"❌ **MARATHON LOSS [{MARATHON['bal_type']}]** -${stake:.2f}\nBal: ${MARATHON['bal']:.2f} / Target ${MARATHON['target']:.2f}\n📉 Compounding reduced - Next Stake: ${marathon_stake():.2f}\n⏳ Resting 90s...")
                if MARATHON["loss_streak"] >= 2:
                    bot.send_message(MARATHON["cid"], "⏸️ 2 losses - Pausing 5 mins to protect balance..."); time.sleep(300)
                    last_trade_time = time.time()
            time.sleep(10)
        except Exception as e:
            print(f"Marathon err {e}")
            try: bot.send_message(MARATHON["cid"], f"⚠️ Marathon error: {e} - retrying in 15s")
            except: pass
            time.sleep(15)
def start_marathon(cid, amount, target=None):
    if target is None: target = float(amount)*2
    MARATHON.update({"active":True,"start":float(amount),"target":float(target),"bal":float(amount),"wins":0,"loss":0,"win_streak":0,"loss_streak":0,"cid":cid,"base_stake":1.0,"marti_level":0})
    bot.send_message(cid, f"🏁 **MARATHON STARTED - SAFE + SMART COMPOUNDING [{MARATHON['bal_type']}]**\n\n💰 Start: ${float(amount):.2f}\n🎯 YOUR Target: ${float(target):.2f}\n💱 Mode: {'Pick One: '+MARATHON_PICK['pair'] if MARATHON_PICK['pair'] else 'Scan All 6 Pairs'}\n⏱️ Expiry: 1 MIN ONLY\n🛡️ Stop Loss: ${float(amount)*0.70:.2f} (Stop if lose 30%)\n📈 Smart Compounding: 10% -> 12% -> 13% -> 14% as you win\n🤖 AUTO PLACE: ON - Bot go place trade for IQ {MARATHON['bal_type']}\n\nScanning now...")
    threading.Thread(target=marathon_loop, daemon=True).start()
def marathon_menu_text(cid):
    bal_type = MARATHON["bal_type"]
    emoji = "🟢 DEMO" if bal_type=="PRACTICE" else "🔴 REAL"
    picked = MARATHON_PICK["pair"] if MARATHON_PICK["pair"] else "Scan All 6 Pairs"
    return f"🏁 **MARATHON MODE - SAFE + SMART COMPOUNDING + CUSTOM TARGET**\n\n💰 Current Balance Mode: {emoji} **{bal_type}**\n🎯 Picked Pair: {picked}\n📊 Pairs: EURUSD, GBPUSD, USDJPY, EURJPY, AUDUSD, USDZAR OTC\n⏱️ Expiry: 1 MIN ONLY\n📈 Smart Compounding: Stake grows as you win\n🛡️ Stop Loss: Stop if lose 30%\n🎯 Custom Target: You choose target\n\n1️⃣ **SCAN ALL** - Bot scans all 6, shows table, picks best\n2️⃣ **PICK ONE** - You pick 1 pair, bot only trades that one\n3️⃣ **AUTO PLACE** - Bot places trade for you on IQ\n\n⚠️ If na REAL, na real money e go use. Double-check before you start!"
def marathon_menu_kb():
    mk = types.InlineKeyboardMarkup(row_width=1)
    if MARATHON["bal_type"]=="PRACTICE":
        mk.add(types.InlineKeyboardButton("🔴 SWITCH TO REAL MONEY",callback_data="mar_bal_REAL"))
    else:
        mk.add(types.InlineKeyboardButton("🟢 SWITCH TO PRACTICE (DEMO)",callback_data="mar_bal_PRACTICE"))
    mk.add(types.InlineKeyboardButton("📊 SCAN ALL 6 PAIRS NOW",callback_data="mar_scan_all"))
    mk.add(types.InlineKeyboardButton("🎯 PICK ONE PAIR",callback_data="mar_pick_menu"))
    mk.add(types.InlineKeyboardButton("📊 SCAN ALL MODE (Clear Pick)",callback_data="mar_scan_all_start"))
    mk.add(types.InlineKeyboardButton("💰 $10 Start",callback_data="mar_ask_start_10"), types.InlineKeyboardButton("💰 $20 Start",callback_data="mar_ask_start_20"))
    mk.add(types.InlineKeyboardButton("🎯 Custom Target",callback_data="mar_custom_target"))
    if MARATHON["active"]:
        mk.add(types.InlineKeyboardButton("🛑 STOP MARATHON",callback_data="mar_stop"))
    return mk
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new_member(m):
    try:
        for member in m.new_chat_members:
            name = member.first_name or "Trader"
            bot.send_message(m.chat.id, f"👋 Welcome {name} to Trailblazer Signals! 🔥\n\n🥇 Forex and GOLD Sniper Signals\n📈 88%+ Accuracy Only\n💰 Stake $1 - Follow Martingale\n📢 Channel: @KEVINTRAILBLAZE\n\nType /welcome to see the rules.\nGood luck! 💪")
    except: pass
@bot.message_handler(commands=['start','stop','mode','balance','results','brain','news','welcome','intro','ready','marathon','real','practice'])
def start(m):
    # Custom target typing - type number for target
    if m.chat.id in MARATHON_TARGET_WAIT and m.text and m.text.replace('.','',1).isdigit():
        start_amt = MARATHON_TARGET_WAIT.pop(m.chat.id)
        target_amt = float(m.text.strip())
        if target_amt <= start_amt:
            bot.send_message(m.chat.id, f"❌ Target must be bigger than start ${start_amt:.0f}. Try again - type target:")
            MARATHON_TARGET_WAIT[m.chat.id] = start_amt
            return
        mkc = types.InlineKeyboardMarkup(row_width=1)
        mkc.add(types.InlineKeyboardButton(f"✅ START ${start_amt:.0f} -> ${target_amt:.0f} (1 MIN)",callback_data=f"mar_target_{start_amt}_{target_amt}"))
        bot.send_message(m.chat.id, f"🎯 Target set: ${target_amt:.0f}\nPress START to begin:", reply_markup=mkc)
        return
    if not is_allowed(m.from_user.id):
        if m.text and m.text.startswith('/welcome'):
            bot.send_message(m.chat.id, WELCOME_TEXT); return
        if m.text and m.text.startswith('/intro'):
            bot.send_message(m.chat.id, INTRO_TEXT); return
        if m.text and m.text.startswith('/ready'):
            bot.send_message(m.chat.id, get_ready_text()); return
        bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/real'):
        MARATHON["bal_type"]="REAL"
        bot.send_message(m.chat.id,"🔴 **MARATHON MODE: REAL MONEY**\n\n⚠️ Next marathon go use REAL balance.\nType /marathon to confirm.",parse_mode="Markdown"); return
    if m.text.startswith('/practice'):
        MARATHON["bal_type"]="PRACTICE"
        bot.send_message(m.chat.id,"🟢 **MARATHON MODE: PRACTICE (DEMO)**\n\n✅ Next marathon go use DEMO balance.\nType /marathon to confirm.",parse_mode="Markdown"); return
    if m.text.startswith('/marathon'):
        bot.send_message(m.chat.id, marathon_menu_text(m.chat.id), reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if m.text.startswith('/welcome'):
        send_photo_to_channel_sync(WELCOME_PHOTO, WELCOME_TEXT)
        bot.send_message(m.chat.id, "✅ Welcome message has been sent to @KEVINTRAILBLAZE with wallpaper! 📤📸"); return
    if m.text.startswith('/intro'):
        send_photo_to_channel_sync(INTRO_PHOTO, INTRO_TEXT)
        bot.send_message(m.chat.id, "✅ Intro message has been sent to @KEVINTRAILBLAZE with wallpaper! 📤📸"); return
    if m.text.startswith('/ready'):
        send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
        bot.send_message(m.chat.id, "✅ Get Ready message has been sent to @KEVINTRAILBLAZE! 🚀📤"); return
    if m.text.startswith('/news'):
        news=get_upcoming_news()
        if not news: bot.send_message(m.chat.id,"📰 **NEWS CHECK**\n\n✅ No high impact news in next 2 hours - Clean market!\n🎯 Safe to trade all pairs.",parse_mode="Markdown"); return
        txt="📰 **UPCOMING NEWS - NEXT 2H**\n\n"+format_news_alert(news)+"⚠️ Bot is blocking these currencies for 30 min before news."; bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/brain'):
        txt="🧠 **AI BRAIN V17 - PAIR LEARNING**\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫 BLOCKED' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 **BEST PAIRS:**\n"+("".join(best) if best else "Not enough data yet\n")+"\n💀 **BAD PAIRS:**\n"+("".join(bad) if bad else "None\n")+"\n⏰ **BEST HOURS + SWEET RSI:**\n"
        for pair,s in PAIR_BRAIN.items():
            if s.get("best_hour") or s.get("best_rsi_range"):
                rng=s.get("best_rsi_range"); rng_txt=f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "Learning..."; txt+=f"{pair}: Best {s.get('best_hour','?')}:00 | Worst {s.get('worst_hour','?')}:00 | Sweet RSI {rng_txt}\n"
        txt+=f"\n📅 Today: {STATS['daily_trades']}/30"
        if is_signal_active(): txt+=f"\n⏳ Active: {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}"
        sb,sn=get_session_boost("EURUSD"); txt+=f"\n⏰ Current Session: {sn} ({sb:+d})"; bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/stop'):
        MARATHON["active"] = False
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id,"🛑 Stopping Marathon + Auto...")
        else: bot.send_message(m.chat.id,"Auto not running"); return
    if m.text.startswith('/results'):
        if not OTC_SESSION_RESULTS: bot.send_message(m.chat.id,"📭 No trades yet this session"); return
        wins=sum(1 for x in OTC_SESSION_RESULTS if x['win']); losses=len(OTC_SESSION_RESULTS)-wins; pnl_total=sum(x['pnl'] for x in OTC_SESSION_RESULTS); idx=OTC_MARTI["loss_streak"]
        txt=f"📊 **RESULTS (1 Real + 3 Marti)**\n\nTotal: {len(OTC_SESSION_RESULTS)} | W:{wins} L:{losses} | PnL: ${pnl_total:.2f}\nToday: {STATS['daily_trades']}/30 | Current: Level {idx+1}/4 | Base: ${OTC_MARTI['base']}\n\n"
        for r in OTC_SESSION_RESULTS[-25:]: txt+=f"{'✅' if r['win'] else '❌'} {r['time']} {r['pair']} {r['dir']} ${r['amt']} L{r['level']} {r['conf']}% {r['pnl']:+.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); sb,sn=get_session_boost("EURUSD")
        txt=f"📍 **MODE CHECK V18 TRAILBLAZER**\n\n{get_greeting()}\n⏰ Now: {now.strftime('%A %H:%M:%S WAT')}\n⏰ Session: {sn} ({sb:+d})\n📊 Mode: {get_mode_text()}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False'}\n🛡️ Martingale: 1 Real + 3 Marti (1-2-4-8)\n📅 Today: {STATS['daily_trades']}/30 trades\n🧠 Brain: {'ON' if PAIR_BRAIN else 'ON - No data yet'}\n📰 News: {len(get_upcoming_news())} high impact in next 2h\n⏳ Active Signal: {ACTIVE_SIGNAL['pair'] if is_signal_active() else 'None'}\nOTC: ⛔ DISABLED - REAL only\n🥇 GOLD: ✅ XAUUSD Scanner ON\n🏁 MARATHON: {'🟢 ACTIVE' if MARATHON['active'] else '⚪ OFF'} | Balance: {MARATHON['bal_type']} | Pick: {MARATHON_PICK['pair'] or 'Scan All'} | Expiry: 1 MIN ONLY | Target: ${MARATHON['target']:.2f}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            if not IQ_CONNECTED: bot.send_message(m.chat.id,f"💰 **BALANCES**\nIQ: ❌ Not connected yet\n📍 {get_mode_text()}\n\nWait 1 min and try /start again"); return
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL"); bot.send_message(m.chat.id,f"💰 **BALANCES**\n🟢 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}\n🏁 MARATHON USING: {MARATHON['bal_type']}\n📍 {get_mode_text()}\n\nTo switch Marathon: /real or /practice or use /marathon button")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    try: bal_demo=get_real_balance("PRACTICE") if IQ_CONNECTED else STATS.get("real_balance",0.0)
    except: bal_demo=0.0
    mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (15) AUTO EXPIRY - ${bal_demo:.2f}",callback_data="trade_real")); mk.add(types.InlineKeyboardButton("🏁 MARATHON 1 MIN",callback_data="marathon_btn")); mk.add(types.InlineKeyboardButton("🚀 GET READY - Send To Channel",callback_data="ready_btn")); mk.add(types.InlineKeyboardButton("📊 MY STATS",callback_data="stats"),types.InlineKeyboardButton("🧠 AI BRAIN",callback_data="brain_btn"),types.InlineKeyboardButton("📰 NEWS CHECK",callback_data="news_btn"),types.InlineKeyboardButton("⚙️ SETTINGS",callback_data="settings"))
    greet=get_greeting(); greet_msg=get_greeting_msg(); sb,sn=get_session_boost("EURUSD")
    txt=f"{greet}\n\n{greet_msg}\n\n🤖 **Z-BOT V18 TRAILBLAZER - MANUAL** 🤖\n\n💎 IQ: {'✅' if IQ_CONNECTED else '❌ False - Retrying...'} | 💰 DEMO ${bal_demo:.2f}\n🏆 W:{STATS['wins']} L:{STATS['loss']} | 🔥 {STATS['streak']}\n📅 Today: {STATS['daily_trades']}/30\n🧠 Brain: Learning best pairs + best hours + sweet RSI\n⏰ Session: {sn} ({sb:+d})\n📰 News: Auto scanner ON\n🥇 GOLD: XAUUSD Scanner ON - Entry/SL/TP\n📍 {get_mode_text()}\n🏁 MARATHON: {MARATHON['bal_type']} - 1 MIN ONLY - Type /marathon\n\n👇 **Select:**\n"
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")
@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="marathon_btn":
        bot.send_message(cid, marathon_menu_text(cid), reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data.startswith("mar_bal_"):
        new_type = data.replace("mar_bal_","")
        if MARATHON["active"]:
            bot.answer_callback_query(c.id,"⚠️ Stop marathon first before switching!")
            bot.send_message(cid,"⚠️ **Cannot switch while Marathon is ACTIVE**\nPress 🛑 STOP first, then switch."); return
        MARATHON["bal_type"]=new_type
        emoji = "🟢 PRACTICE (DEMO)" if new_type=="PRACTICE" else "🔴 REAL MONEY"
        bot.answer_callback_query(c.id,f"Switched to {new_type}")
        bot.send_message(cid, f"✅ **SWITCHED TO {emoji}**\n\n🏁 Next Marathon go use {new_type} balance.\nType /marathon to see menu.", reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data=="mar_scan_all":
        txt, results = marathon_scan_all_text()
        mk = types.InlineKeyboardMarkup(row_width=2)
        if results: mk.add(types.InlineKeyboardButton(f"✅ AUTO TRADE BEST {results[0]['pair']}",callback_data="mar_ask_start_10"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN",callback_data="mar_scan_all"))
        mk.add(types.InlineKeyboardButton("🎯 PICK ONE",callback_data="mar_pick_menu"))
        bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown"); return
    if data=="mar_pick_menu":
        mk = types.InlineKeyboardMarkup(row_width=1)
        for p in MARATHON_PAIRS:
            mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"mar_pick_{p}"))
        mk.add(types.InlineKeyboardButton("📊 SCAN ALL INSTEAD",callback_data="mar_scan_all_start"))
        bot.send_message(cid, "🎯 **PICK ONE PAIR FOR MARATHON - 1 MIN ONLY**\n\nBot go only trade this pair until you stop.\nPick one:", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mar_pick_"):
        pair = data.replace("mar_pick_","")
        MARATHON_PICK["pair"] = pair
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💰 $10 Start",callback_data="mar_ask_start_10"), types.InlineKeyboardButton("💰 $20 Start",callback_data="mar_ask_start_20"))
        bot.send_message(cid, f"✅ **PICKED: {PAIR_EMOJI.get(pair,pair)}**\n💰 Balance: {MARATHON['bal_type']} | ⏱️ Expiry: 1 MIN ONLY\n\nNow choose $10 or $20 to start, then choose your target.", reply_markup=mk, parse_mode="Markdown"); return
    if data=="mar_scan_all_start":
        MARATHON_PICK["pair"] = None
        bot.send_message(cid, "📊 Scan All mode ON - Bot go pick best pair each time. 1 MIN ONLY.", reply_markup=marathon_menu_kb(), parse_mode="Markdown"); return
    if data=="mar_custom_target":
        # Ask start first, then target
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💰 $10 Start",callback_data="mar_ask_start_10"), types.InlineKeyboardButton("💰 $20 Start",callback_data="mar_ask_start_20"))
        bot.send_message(cid, "🎯 **CUSTOM TARGET**\n\nFirst pick your START amount, then you go choose target:", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mar_ask_start_"):
        amt = float(data.replace("mar_ask_start_",""))
        MARATHON["start"] = amt
        mk2 = types.InlineKeyboardMarkup(row_width=2)
        mk2.add(types.InlineKeyboardButton(f"🎯 Target ${amt*1.5:.0f} (+50%)",callback_data=f"mar_target_{amt}_{amt*1.5}"))
        mk2.add(types.InlineKeyboardButton(f"🎯 Target ${amt*2:.0f} (Double)",callback_data=f"mar_target_{amt}_{amt*2}"))
        mk2.add(types.InlineKeyboardButton(f"🎯 Target ${amt*3:.0f} (Triple)",callback_data=f"mar_target_{amt}_{amt*3}"))
        mk2.add(types.InlineKeyboardButton(f"✍️ Type My Own Target",callback_data=f"mar_type_target_{amt}"))
        bot.send_message(cid, f"💰 Start: ${amt:.0f} | Balance: {MARATHON['bal_type']} | ⏱️ 1 MIN ONLY\n\n🎯 **Choose Your Target:**\nYou fit pick double, triple, or type your own.", reply_markup=mk2, parse_mode="Markdown"); return
    if data.startswith("mar_type_target_"):
        amt = float(data.replace("mar_type_target_",""))
        MARATHON_TARGET_WAIT[cid] = amt
        bot.send_message(cid, f"✍️ **Type your target amount**\n\nStart: ${amt:.0f}\n⏱️ Expiry: 1 MIN ONLY\nExample: type `25` if you want target $25\n\nJust type the number now:"); return
    if data.startswith("mar_target_"):
        parts = data.replace("mar_target_","").split("_")
        start_amt = float(parts[0]); target_amt = float(parts[1])
        if MARATHON["active"]: bot.answer_callback_query(c.id,"Marathon already running"); return
        if MARATHON["bal_type"]=="REAL":
            mk3 = types.InlineKeyboardMarkup(row_width=2)
            mk3.add(types.InlineKeyboardButton(f"✅ YES REAL ${start_amt:.0f} -> ${target_amt:.0f} (1 MIN)",callback_data=f"mar_confirm_custom_{start_amt}_{target_amt}"), types.InlineKeyboardButton("❌ NO, PRACTICE",callback_data="mar_bal_PRACTICE"))
            bot.send_message(cid, f"⚠️ **CONFIRM REAL MONEY - 1 MIN ONLY**\nStart ${start_amt:.0f} -> Target ${target_amt:.0f}\nPair: {MARATHON_PICK['pair'] or 'Scan All'}\nStop Loss: ${start_amt*0.70:.2f}", reply_markup=mk3, parse_mode="Markdown"); return
        start_marathon(cid, start_amt, target_amt); return
    if data.startswith("mar_confirm_custom_"):
        parts = data.replace("mar_confirm_custom_","").split("_")
        start_amt = float(parts[0]); target_amt = float(parts[1])
        start_marathon(cid, start_amt, target_amt); return
    if data.startswith("mar_start_"):
        amt = float(data.replace("mar_start_",""))
        if MARATHON["active"]: bot.answer_callback_query(c.id,"Marathon already running"); return
        # Old button fallback - ask target
        MARATHON["start"] = amt
        mk2 = types.InlineKeyboardMarkup(row_width=2)
        mk2.add(types.InlineKeyboardButton(f"🎯 Target ${amt*2:.0f} (Double)",callback_data=f"mar_target_{amt}_{amt*2}"))
        mk2.add(types.InlineKeyboardButton(f"✍️ Type My Own",callback_data=f"mar_type_target_{amt}"))
        bot.send_message(cid, f"💰 Start ${amt:.0f} - Choose target:", reply_markup=mk2, parse_mode="Markdown"); return
    if data == "mar_stop":
        MARATHON["active"] = False; clear_signal()
        bot.send_message(cid, f"🛑 **MARATHON STOPPED [{MARATHON['bal_type']}]**\nBal: ${MARATHON['bal']:.2f} | Target was ${MARATHON['target']:.2f} | W:{MARATHON['wins']} L:{MARATHON['loss']}"); return
    if data=="ready_btn":
        send_photo_to_channel_sync(READY_PHOTO, get_ready_text())
        bot.answer_callback_query(c.id,"✅ Get Ready sent to Channel!")
        bot.send_message(cid,"✅ Get Ready message has been sent to @KEVINTRAILBLAZE! 🚀📤"); return
    if data.startswith("send_channel_pb_"):
        try:
            parts=data.replace("send_channel_pb_","").rsplit("_",1); pair=parts[0]; dir_ = parts[1] if len(parts)>1 else ACTIVE_SIGNAL.get("dir","CALL")
            tz2=pytz.timezone("Africa/Lagos"); entry_txt=(datetime.now(tz2)+timedelta(seconds=45)).strftime('%H:%M:%S WAT')
            idx = OTC_MARTI["loss_streak"]
            if idx < 1: idx = 1
            if idx > 3: idx = 3
            amt = OTC_MARTI["base"] * OTC_MARTI["levels"][idx]
            expiry = ACTIVE_SIGNAL.get("expiry", 60)
            if pair=="XAUUSD": send_to_channel_sync(format_channel_pullback_gold_signal(dir_, entry_txt, idx, amt))
            else: send_to_channel_sync(format_channel_pullback_signal(pair, dir_, entry_txt, idx, amt, expiry))
            bot.answer_callback_query(c.id,"✅ Brief pullback sent to Channel!")
            bot.send_message(cid,"✅ Brief pullback signal sent to @KEVINTRAILBLAZE 📤")
        except Exception as e: bot.answer_callback_query(c.id,f"Error {e}")
        return
    if data.startswith("send_channel_"):
        try:
            parts=data.replace("send_channel_","").rsplit("_",1); pair=parts[0]; dir_ = parts[1] if len(parts)>1 else ACTIVE_SIGNAL.get("dir","CALL")
            tz2=pytz.timezone("Africa/Lagos"); entry_txt=(datetime.now(tz2)+timedelta(seconds=45)).strftime('%H:%M:%S WAT')
            expiry = ACTIVE_SIGNAL.get("expiry", 60)
            if pair=="XAUUSD":
                if ACTIVE_SIGNAL.get("sl",0) and ACTIVE_SIGNAL.get("pair")=="XAUUSD":
                    d_gold = {"dir":dir_, "conf":ACTIVE_SIGNAL.get("conf",88), "price":ACTIVE_SIGNAL.get("price",0), "sl":ACTIVE_SIGNAL.get("sl",0), "tp1":ACTIVE_SIGNAL.get("tp1",0), "tp2":ACTIVE_SIGNAL.get("tp2",0)}
                    send_to_channel_sync(format_channel_gold_signal(d_gold, entry_txt))
                else: send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("price",0), entry_txt, expiry))
            else: send_to_channel_sync(format_channel_signal(pair, dir_, ACTIVE_SIGNAL.get("conf",88), ACTIVE_SIGNAL.get("price",0), entry_txt, expiry))
            bot.answer_callback_query(c.id,"✅ Sent to @KEVINTRAILBLAZE!")
            bot.send_message(cid,"✅ Simple signal has been sent to @KEVINTRAILBLAZE 📤")
        except Exception as e: bot.answer_callback_query(c.id,f"Error {e}")
        return
    if data=="news_btn":
        news=get_upcoming_news()
        if not news: bot.send_message(cid,"📰 **NEWS CHECK**\n\n✅ No high impact news in next 2 hours - Clean market!\n🎯 Safe to trade all pairs.",parse_mode="Markdown"); return
        txt="📰 **UPCOMING NEWS - NEXT 2H**\n\n"+format_news_alert(news)+"⚠️ Bot is blocking these currencies for 30 min before news."; bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data.startswith("skip_"):
        pair=data.replace("skip_","")
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); LAST_GLOBAL_SIGNAL["time"]=time.time()-(GLOBAL_COOLDOWN-SKIP_COOLDOWN); bot.answer_callback_query(c.id,"Skipped - Next in 5 min"); bot.send_message(cid,f"⏭️ **SKIPPED**\n\n💱 {pair}\nYou skipped this trade.\nNo WIN / LOSS recorded.\n⏳ Next signal in **5 mins**.\n✅ Lock opened."); return
    if data.startswith("manual_win_"):
        pair=data.replace("manual_win_",""); win_conf=ACTIVE_SIGNAL.get("conf",88); win_rsi=ACTIVE_SIGNAL.get("rsi",50); win_adx=ACTIVE_SIGNAL.get("adx",30); win_dir=ACTIVE_SIGNAL.get("dir","CALL")
        record_brain(pair,True,win_conf,win_rsi,win_adx); OTC_MARTI["loss_streak"]=0
        if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
        clear_signal(); STATS['wins']+=1; count_trade(); wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR now {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,"WIN 🏅")
        base=OTC_MARTI["base"]; profit=round(base*0.85,2); total_return=round(base+profit,2); tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); dir_e="🟢 CALL ⬆️" if win_dir=="CALL" else "🔴 PUT ⬇️"; total=STATS['wins']+STATS['loss']; wr_total=(STATS['wins']/total*100) if total else 0
        win_msg=f"🏆━━━━━━━━━━━━━━━━━━🏆\n      ✅ TRADE WON 🏅\n🏆━━━━━━━━━━━━━━━━━━🏆\n\n🎯 {PAIR_EMOJI.get(pair,pair)}\n📈 {dir_e} | Conf: {win_conf:.0f}%\n🕒 {now.strftime('%H:%M:%S')} | {now.strftime('%d %b')}\n\n──────────────────\n💵 Stake: ${base:.2f}\n💰 Profit: +${profit:.2f}\n💵 Payout: ${total_return:.2f}\n──────────────────\n\n🏅 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']}\n📊 Today WR: {wr_total:.1f}%{wr_txt}\n♻️ Next Entry Reset: ${base:.2f}\n🔍 Pullback scan STOPPED\n📅 Today: {STATS['daily_trades']}/30 trades\n✅ Next signal can now come.\n"
        bot.send_message(cid,win_msg,parse_mode="Markdown"); bot.send_message(cid,"🤑"); return
    if data.startswith("manual_loss_"):
        parts=data.replace("manual_loss_","").rsplit("_",1); pair=parts[0]; orig_dir=parts[1] if len(parts)>1 else "CALL"
        record_brain(pair,False,ACTIVE_SIGNAL.get("conf",88),ACTIVE_SIGNAL.get("rsi",50),ACTIVE_SIGNAL.get("adx",30)); OTC_MARTI["loss_streak"]+=1; STATS['loss']+=1; count_trade()
        if OTC_MARTI["loss_streak"]>=4:
            OTC_MARTI["loss_streak"]=0
            if cid in PULLBACK_STATE: PULLBACK_STATE[cid]["active"]=False
            clear_signal(); wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR now {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,"Chain finished - Reset to $1"); bot.send_message(cid,f"⛔ **CHAIN FINISHED**\n\n💱 {pair}\n❌ Lost: $1 + $2 + $4 + $8 = -$15\n♻️ RESET to Real Entry $1\n🛑 No more martingale for this pair.{wr_txt}\n📅 Today: {STATS['daily_trades']}/30\n✅ Next signal can now come.\n💪 Do not give up Trailblazer! 🔥"); return
        levels=OTC_MARTI["levels"]; idx=OTC_MARTI["loss_streak"]; mult=levels[idx]; next_amt=OTC_MARTI["base"]*mult; names=["","Martingale 1","Martingale 2","Martingale 3"]; wr=get_pair_winrate(pair); wr_txt=f"\n🧠 {pair} Brain WR {wr:.0f}%" if wr is not None else ""; bot.answer_callback_query(c.id,f"LOSS - Next {names[idx]} ${next_amt}"); bot.send_message(cid,f"❌ **LOSS Recorded**\n\n💱 {pair}\n👉 Next: **{names[idx]} - ${next_amt:.2f} Level {idx+1}/4 ({mult}x)**{wr_txt}\n🔍 Scanning every 10 sec for pullback entry...\n📍 RSI7 + RSI14 safe + RSI turning + Price at EMA\n📰 News check ON\n\nPress ✅ WIN / ❌ LOSS / ⏭️ SKIP after you trade it manually.")
        threading.Thread(target=pullback_scanner_loop,args=(cid,pair,orig_dir),daemon=True).start(); return
    if data=="brain_btn":
        txt="🧠 **AI BRAIN V18**\n\n"; best=[]; bad=[]
        for pair,s in PAIR_BRAIN.items():
            total=s["wins"]+s["loss"]
            if total>=3:
                wr=s["wins"]/total*100; line=f"{PAIR_EMOJI.get(pair,pair)}: W{s['wins']} L{s['loss']} = {wr:.0f}% {'🚫' if is_pair_blocked(pair) else ''}\n"
                if wr>=60: best.append(line)
                elif wr<50: bad.append(line)
        txt+="🏆 BEST:\n"+("".join(best) if best else "No data yet\n")+"\n💀 BAD:\n"+("".join(bad) if bad else "None\n")+"\n⏰ **BEST HOURS + SWEET RSI:**\n"
        for pair,s in PAIR_BRAIN.items():
            if s.get("best_hour") or s.get("best_rsi_range"):
                rng=s.get("best_rsi_range"); rng_txt=f"{rng[0]:.0f}-{rng[1]:.0f}" if rng else "Learning..."; txt+=f"{pair}: Best {s.get('best_hour','?')}:00 | Worst {s.get('worst_hour','?')}:00 | Sweet RSI {rng_txt}\n"
        sb,sn=get_session_boost("EURUSD"); txt+=f"\n⏰ Now: {sn} ({sb:+d})"; bot.send_message(cid,txt,parse_mode="Markdown"); return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1); mk.add(types.InlineKeyboardButton("🔍 📊 SCAN ALL REAL NOW (15 PAIRS)",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        mk.add(types.InlineKeyboardButton("🥇 XAU/USD GOLD",callback_data="real_pair_XAUUSD"))
        bot.send_message(cid,f"📈 **TRADE REAL V18 TRAILBLAZER MANUAL**\n📍 {get_mode_text()}\n📅 Today: {STATS['daily_trades']}/30",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        if is_signal_active(): bot.send_message(cid,f"⏳ **One signal already active**\n\n💱 {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP"); return
        if not can_trade_today(): bot.send_message(cid,"⛔ Max 30 trades reached today. Come back tomorrow 7AM."); return
        bot.answer_callback_query(c.id,"Scanning 15 REAL pairs V18..."); scan_msg=bot.send_message(cid,"🔍 **SCANNING ALL 15 REAL PAIRS V18 TRAILBLAZER...**\n\n⏳ ~12 sec"); results=[]; datas={}
        for pair in REAL_PAIRS:
            if is_pair_blocked(pair): results.append((pair,0,"-","🧠 Blocked","🔴 BLOCKED",60)); continue
            nb=is_news_blocking_pair(pair,minutes=30)
            if nb: results.append((pair,0,"-","📰 News Block","🔴 NEWS",60)); continue
            d=analyze_sniper_v12(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴 NO TRADE",60)); continue
            conf=d['conf']; dir_=d['dir']; reason=d['reason']; exp=d['expiry']
            if conf>=88: status="🟢 READY"
            elif conf>=65: status="🟡 WAIT"
            else: status="🔴 NO TRADE"
            results.append((pair,conf,dir_,reason,status,exp)); datas[pair]=d
            try: bot.edit_message_text(f"🔍 Scanning V18... {pair} {conf:.0f}%",cid,scan_msg.message_id)
            except: pass
            time.sleep(0.3)
        results.sort(key=lambda x:x[1],reverse=True); txt="📊 **REAL V18 TRAILBLAZER READINESS** 📊\n"; txt+=f"📍 {get_mode_text()}\n⏰ {datetime.now(pytz.timezone('Africa/Lagos')).strftime('%H:%M:%S WAT')}\n📅 Today: {STATS['daily_trades']}/30\n📰 News: {len(get_upcoming_news())} high impact in next 2h\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            if conf>=65: txt+=f"{status} {emoji}: {conf:.0f}% {dir_} - {reason}\n"
            else: txt+=f"{status} {emoji}: {conf:.0f}% - {reason}\n"
        best=results[0] if results else None
        if best and best[1]>=88: txt+=f"\n💡 **BEST NOW:** {PAIR_EMOJI.get(best[0],best[0])} {best[1]:.0f}%"
        mk=types.InlineKeyboardMarkup(row_width=2)
        if best and best[1]>=88: mk.add(types.InlineKeyboardButton(f"✅ TRADE BEST {best[0]}",callback_data=f"real_pair_{best[0]}"))
        mk.add(types.InlineKeyboardButton("🔄 RE-SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,txt,reply_markup=mk,parse_mode="Markdown")
        if best and best[1]>=88 and best[0] in datas:
            time.sleep(0.5); best_data=datas[best[0]]; tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if best_data['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
            mk2=types.InlineKeyboardMarkup(row_width=2); mk2.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_{best_data['pair']}"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_{best_data['pair']}_{best_data['dir']}")); mk2.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{best_data['pair']}")); mk2.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_{best_data['pair']}_{best_data['dir']}"))
            signal_txt=f"📡 **REAL TOP SIGNAL V18 - MANUAL** 📡\n\n💱 {PAIR_EMOJI.get(best_data['pair'],best_data['pair'])}\n📊 {dir_e} | 🎯 {best_data['conf']:.0f}% SNIPER\n📈 {best_data['reason']} | RSI {best_data['rsi']:.1f}\n💸 {int(best_data['payout']*100)}% | 💰 {best_data['price']:.5f} | ⏱️ Suggested: 1 Min\n📊 Trend: {best_data.get('trend_info',{}).get('trend_type','➡️ NORMAL TREND')}\n📰 News: ✅ Checked\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Real Entry:** ${base:.2f}\n**Marti 1:** ${base*2:.2f} | **Marti 2:** ${base*4:.2f} | **Marti 3:** ${base*8:.2f}\n\n⚠️ MANUAL - Press WIN / LOSS / SKIP\n"
            bot.send_message(cid,signal_txt,parse_mode="Markdown",reply_markup=mk2); start_signal(best_data['pair'],best_data['dir'],best_data['conf'],best_data['rsi'],best_data.get('adx',30), price=best_data['price'], expiry=60)
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        if pair=="XAUUSD":
            bot.answer_callback_query(c.id,"Scanning GOLD..."); d=analyze_xauusd()
            if not d: bot.send_message(cid,"⚠️ **No safe GOLD trade now**\n\n📊 Conf < 88% or ADX / News block\nTry again in 5 min."); return
            tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry_time=now+timedelta(seconds=45); dir_e="🟢 BUY ⬆️" if d['dir']=="CALL" else "🔴 SELL ⬇️"; base=OTC_MARTI["base"]
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN```python
            mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data="manual_win_XAUUSD"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_XAUUSD_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data="skip_XAUUSD")); mk.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_XAUUSD_{d['dir']}"))
            msg=f"🥇🥇🥇 **XAU/USD GOLD SIGNAL** 🥇🥇🥇\n\n{dir_e} | 🎯 {d['conf']:.0f}% SNIPER GOLD\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.2f}\n⏰ Session: {d['session']}\n\n━━━━━━━━━━━━━━━━━━\n⏰ ENTRY TIME: {entry_time.strftime('%H:%M:%S WAT')}\n💰 ENTRY: {d['price']:.2f}\n🛑 SL: {d['sl']:.2f}\n🎯 TP1: {d['tp1']:.2f} (1:1 Secure)\n🎯 TP2: {d['tp2']:.2f} (1:2 Runner)\n━━━━━━━━━━━━━━━━━━\n\n💵 **Stake:** ${base:.2f}\n⚠️ MANUAL - Press WIN / LOSS / SKIP\n"
            bot.send_message(cid,msg,parse_mode="Markdown",reply_markup=mk); start_signal("XAUUSD",d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], sl=d['sl'], tp1=d['tp1'], tp2=d['tp2']); return
        if is_signal_active() and ACTIVE_SIGNAL['pair']!=pair: bot.send_message(cid,f"⏳ **One signal already active**\n\n💱 {ACTIVE_SIGNAL['pair']} {ACTIVE_SIGNAL['dir']}\nFinish it first - Press ✅ WIN / ❌ LOSS / ⏭️ SKIP"); return
        if is_pair_blocked(pair): bot.send_message(cid,f"🧠 **{pair} Blocked by Brain**\n\nThis pair has been losing. Brain blocked it for 2h.\nTry another pair or /brain"); return
        nb=is_news_blocking_pair(pair,minutes=30)
        if nb: bot.send_message(cid,f"📰 **{pair} Blocked by NEWS**\n\n🔴 {nb['country']} - {nb['title']}\n⏰ In {nb['in_min']} min\n\nWait 15 min after news."); return
        bot.answer_callback_query(c.id,f"Scanning {pair} V18..."); scan_msg=bot.send_message(cid,f"🔍 **V18 TRAILBLAZER SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Sniper..."); legit_live_scan(cid,scan_msg.message_id,pair); d=analyze_sniper_v12(pair,sniper_mode=False)
        if not d or d['conf']<88:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real")); bot.send_message(cid,f"⚠️ **No safe trade now for {pair}**\n\n📊 Conf: {d['conf'] if d else 0}% < 88%\n🛡️ {d['reason'] if d else 'No data'}",reply_markup=mk); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=45); dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"; base=OTC_MARTI["base"]
        signal_txt=f"📡 **REAL SIGNAL V18 TRAILBLAZER - MANUAL** 📡\n\n💱 {PAIR_EMOJI.get(pair,pair)}\n📊 {dir_e} | 🎯 {d['conf']:.0f}% SNIPER\n📈 {d['reason']} | RSI {d['rsi']:.1f} | ATR {d['atr']:.5f}\n📊 Trend: {d.get('trend_info',{}).get('trend_type','➡️ NORMAL TREND')}\n🔍 Trends: {' | '.join(d.get('trend_info',{}).get('trends',[])[:4])}\n💸 {int(d['payout']*100)}% | 💰 {d['price']:.5f} | ⏱️ Suggested: 1 Min\n📰 News: ✅ Checked\n\n⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in 45s)\n\n**Real Entry:** ${base:.2f}\n**Marti 1:** ${base*2:.2f} | **Marti 2:** ${base*4:.2f} | **Marti 3:** ${base*8:.2f}\n\n⚠️ **MANUAL PLACE - Press WIN / LOSS / SKIP**\n"
        mk=types.InlineKeyboardMarkup(row_width=2); mk.add(types.InlineKeyboardButton("✅ WIN - Reset",callback_data=f"manual_win_{pair}"),types.InlineKeyboardButton("❌ LOSS - Pullback Scan",callback_data=f"manual_loss_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("⏭️ SKIP THIS TRADE",callback_data=f"skip_{pair}")); mk.add(types.InlineKeyboardButton("📤 Send to Channel",callback_data=f"send_channel_{pair}_{d['dir']}")); mk.add(types.InlineKeyboardButton("🔁 SAME PAIR",callback_data=f"real_pair_{pair}"),types.InlineKeyboardButton("📈 SCAN ALL",callback_data="scan_all_real"))
        bot.send_message(cid,signal_txt,reply_markup=mk,parse_mode="Markdown"); start_signal(pair,d['dir'],d['conf'],d['rsi'],d.get('adx',30), price=d['price'], expiry=60); return
    if data=="trade" or data=="scan_all_otc" or data=="auto_setup" or data.startswith("auto_pair_") or data.startswith("auto_bal_") or data.startswith("auto_amt_") or data.startswith("pair_"):
        bot.answer_callback_query(c.id,"OTC Disabled"); bot.send_message(cid,"⛔ **OTC DISABLED**\n\nOTC is causing delays. Bot will only send REAL signals from 7AM.\n\nUse TRADE REAL for now."); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid,"🛑 Stopping..."); return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0; bal=get_real_balance("PRACTICE"); sb,sn=get_session_boost("EURUSD"); bot.send_message(cid,f"📊 **STATS V18**\n📍 {get_mode_text()}\n{get_greeting()}\n⏰ Session: {sn} ({sb:+d})\n🏆 Wins: {STATS['wins']}\n❌ Loss: {STATS['loss']}\n📈 Winrate: {wr:.1f}%\n🔥 Streak: {STATS['streak']}\n💰 Bal: ${bal:.2f}\n📅 Today: {STATS['daily_trades']}/30\n🧠 Brain pairs: {len(PAIR_BRAIN)}\n📰 News in 2h: {len(get_upcoming_news())}\n📦 OTC: DISABLED | REAL only\n🥇 GOLD: XAUUSD ON\n🏁 MARATHON: {MARATHON['bal_type']} | 1 MIN ONLY | Target: ${MARATHON['target']:.2f}",parse_mode="Markdown")
    if data=="settings": bot.send_message(cid,f"⚙️ **SETTINGS V18 TRAILBLAZER MANUAL**\n\n🛡️ V18: 5M Trend + ADX 25+ + MACD + Stochastic + BB + Payout 80%+ + News Block + Session Boost + Brain + Pullback\n📈 Marathon: Smart Compounding 10% -> 14% | Stop Loss 30% | 1 MIN ONLY | Custom Target\n\n📢 Channel: @KEVINTRAILBLAZE\nUse /welcome, /intro and /ready to post to channel.")
if __name__ == "__main__":
    print("Starting Trailblazer Bot - SAFE + COMPOUNDING + CUSTOM TARGET + 1 MIN MARATHON...")
    try:
        bot.remove_webhook()
        time.sleep(1)
    except: pass
    threading.Thread(target=background_iq, daemon=True).start()
    threading.Thread(target=daily_summary_loop, daemon=True).start()
    threading.Thread(target=trailblazer_market_scanner, daemon=True).start()
    threading.Thread(target=morning_greet_loop, daemon=True).start()
    threading.Thread(target=xauusd_signal_scanner, daemon=True).start()
    threading.Thread(target=real_signal_scanner, daemon=True).start()
    def run_polling():
        while True:
            try:
                print("Bot polling started...")
                bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except Exception as e:
                print(f"Polling error: {e} - Retrying in 5 seconds...")
                time.sleep(5)
    threading.Thread(target=run_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
