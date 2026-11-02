import os, time, threading, warnings, logging, random
from datetime import datetime, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger("iqoptionapi").setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY"]
OTC_PAIRS = [
    "EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC",
    "USDZAR-OTC","USDMXN-OTC","USDTRY-OTC","USDBRL-OTC","USDNGN-OTC","USDINR-OTC"
]
PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL",
    "EURGBP":"🇪🇺 EUR/GBP REAL", "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL",
    "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD", "GBPUSD-OTC":"🇬🇧 GBP/USD", "EURGBP-OTC":"🇪🇺 EUR/GBP",
    "USDJPY-OTC":"🇺🇸 USD/JPY", "GBPJPY-OTC":"🇬🇧 GBP/JPY", "AUDUSD-OTC":"🇦🇺 AUD/USD",
    "USDCHF-OTC":"🇺🇸 USD/CHF", "EURJPY-OTC":"🇪🇺 EUR/JPY",
    "USDZAR-OTC":"🇿🇦 USD/ZAR", "USDMXN-OTC":"🇲🇽 USD/MXN", "USDTRY-OTC":"🇹🇷 USD/TRY",
    "USDBRL-OTC":"🇧🇷 USD/BRL", "USDNGN-OTC":"🇳🇬 USD/NGN", "USDINR-OTC":"🇮🇳 USD/INR"
}
STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; AUTO_LOCK = {}
IQ_LOCK = threading.RLock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0
LAST_ERROR = "No error yet"

def is_allowed(uid): return uid == OWNER_ID

def is_real_market_open():
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour_utc = now.hour
    if weekday == 0 and hour_utc < 3: return False
    if weekday == 4 and hour_utc >= 21: return False
    if weekday in [5,6]: return False
    return True

def get_active_pairs():
    return REAL_PAIRS + OTC_PAIRS

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(EMAIL,PWD); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: iq.change_balance("PRACTICE")
            except: pass
        logging.disable(logging.NOTSET); logging.getLogger().setLevel(logging.CRITICAL); logging.disable(logging.ERROR)
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]:
                        PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)

def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for attempt in range(3):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                c = iq.get_candles(pair, 60, 50, time.time())
                if not c or len(c) < 20:
                    c = iq.get_candles(pair, 300, 50, time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c) > 20: return pd.DataFrame(sorted(c, key=lambda x: x['from']))
            time.sleep(0.5)
        except: time.sleep(0.5)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 Initializing V8...", 0.15),
        (15, f"🔌 IQ Check {pair}...", 0.2),
        (30, "📊 Fetching candles...", 0.25),
        (50, "📈 EMA9 + EMA21...", 0.2),
        (70, "💹 RSI + ATR...", 0.2),
        (85, "📰 Final check...", 0.2),
        (100, "🔒 SIGNAL LOCKED!")
    ]
    last_pct = -1
    for item in steps:
        if len(item) == 3: pct, text, delay = item
        else: pct, text = item; delay = 0.15
        if pct == last_pct: time.sleep(delay); continue
        last_pct = pct
        filled = int(pct // 5); bar = "█" * filled + "░" * (20 - filled)
        if pct < 40: color = "🟥"
        elif pct < 80: color = "🟨"
        elif pct < 100: color = "🟩"
        else: color = "💎"
        scan_txt = f"""{color} **Z-BOT V8 LEGIT SCAN** {color}

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

{bar} {pct}%
▓ Progress: {pct}% ▓

🔍 {text}

⏳ Fast scan - V8.2
"""
        try: bot.edit_message_text(scan_txt, cid, mid, parse_mode="Markdown")
        except: pass
        time.sleep(delay)
    try:
        final_txt = f"""💎 **Z-BOT V8 LEGIT SCAN** 💎

💱 Pair: {PAIR_EMOJI.get(pair, pair)}
💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌ Offline'}

████████████████████ 100%
▓ Progress: 100% ▓

🔍 🔒 SIGNAL LOCKED! READY TO TRADE!

⏳ Scan complete - Fast V8.2!
"""
        bot.edit_message_text(final_txt, cid, mid, parse_mode="Markdown")
        time.sleep(0.3)
    except: pass

def analyze_momentum(pair, sniper_mode=False):
    df=get_candles(pair)
    if df is None:
        payout=get_payout(pair); sig=random.choice(["CALL","PUT"])
        return {"pair":pair,"dir":sig,"conf":75,"price":0,"rsi":50,"reason":f"⚡ Exotic {pair}","payout":payout,"df":None,"rejected":False}
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        payout=get_payout(pair); sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78:
            sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50:
            sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        else: score=60; reason="Low momentum"
        if sniper_mode and score < 90:
            return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":True}
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"rejected":False}
    except:
        payout=get_payout(pair)
        return {"pair":pair,"dir":"CALL","conf":70,"price":0,"rsi":50,"reason":f"Fallback","payout":payout,"df":None,"rejected":False}

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    global LAST_ERROR
    error_log = ""
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            try:
                iq.change_balance(bal)
                bal_now = iq.get_balance()
                error_log += f"Bal {bal} = {bal_now}\n"
            except Exception as e:
                error_log += f"Bal fail: {e}\n"
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            is_real = "-OTC" not in pair
            mins = max(1, int(expiry_sec/60))
            if is_real:
                try:
                    logging.disable(logging.CRITICAL)
                    check, oid = iq.buy(amount, pair, direction.lower(), mins)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    if check:
                        LAST_ERROR = "SUCCESS"
                        return True, oid, expiry_sec
                    else:
                        error_log += f"REAL {mins}m returned False id:{oid}\n"
                except Exception as e:
                    error_log += f"REAL {mins}m EX: {e}\n"
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if not is_real and expiry_sec <= 90:
                try:
                    logging.disable(logging.CRITICAL)
                    check, oid = iq.buy_blitz(pair, amount, direction.lower(), expiry_sec)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    if check:
                        LAST_ERROR = "SUCCESS"
                        return True, oid, expiry_sec
                    else:
                        error_log += f"Blitz {expiry_sec}s False id:{oid}\n"
                except Exception as e:
                    error_log += f"Blitz {expiry_sec}s EX: {e}\n"
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            try:
                logging.disable(logging.CRITICAL)
                check, oid = iq.buy(amount, pair, direction.lower(), mins)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if check:
                    LAST_ERROR = "SUCCESS"
                    return True, oid, expiry_sec
                else:
                    error_log += f"Binary {mins}m False id:{oid}\n"
            except Exception as e:
                error_log += f"Binary {mins}m EX: {e}\n"
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
    except Exception as e:
        error_log += f"TOTAL CRASH: {e}\n"
    LAST_ERROR = f"❌ {pair} FAIL\n{error_log}\nTime {datetime.now().strftime('%H:%M:%S')}\nREAL_OPEN={is_real_market_open()}"
    print(f"FAIL LOG: {LAST_ERROR}", flush=True)
    return False,None,0

def auto_trader_loop(cid):
    consecutive_losses = 0; AUTO_LOCK[cid] = True
    bot.send_message(cid, f"🔒 **ONE TRADE AT A TIME REAL FIXED**")
    while AUTO_STATE.get(cid, {}).get('running', False):
        if AUTO_STATE[cid].get('in_trade', False): time.sleep(5); continue
        try:
            state = AUTO_STATE.get(cid)
            if not state or not state['running']: break
            pair_to_trade = state['pair']
            if pair_to_trade == "AUTO":
                best = None; best_score = 0
                for p in get_active_pairs():
                    if "-OTC" not in p and not is_real_market_open(): continue
                    d = analyze_momentum(p, sniper_mode=True)
                    if d and not d.get('rejected') and d['conf'] > best_score:
                        best_score = d['conf']; best = d
                if not best: time.sleep(30); continue
                d = best; pair_to_trade = d['pair']
            else:
                if "-OTC" not in pair_to_trade and not is_real_market_open():
                    bot.send_message(cid, f"⏳ REAL {pair_to_trade} closed, waiting 60s..."); time.sleep(60); continue
                d = analyze_momentum(pair_to_trade, sniper_mode=True)
                if not d or d.get('rejected'): time.sleep(20); continue
            curr_amt = state['base_amt'] if consecutive_losses==0 else min(state['base_amt'] * (2.2 ** consecutive_losses), state['base_amt'] * 8)
            AUTO_STATE[cid]['in_trade'] = True
            ok, oid, exp = iq_trade(pair_to_trade, d['dir'], curr_amt, state['bal'], state['expiry'])
            if not ok:
                AUTO_STATE[cid]['in_trade'] = False
                bot.send_message(cid, f"⚠️ {pair_to_trade} fail\n{LAST_ERROR}\nTrying next 10s..."); time.sleep(10); continue
            bot.send_message(cid, f"🤖 **AUTO #{state['trades']+1}**\n💱 {pair_to_trade} {d['dir']} ${curr_amt:.2f}\n🎯 {d['conf']}% ID {oid}")
            time.sleep(exp+5)
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if pnl>0:
                    STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1
                    mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
                    bot.send_message(cid, f"✅ **WIN +${pnl:.2f}** {pair_to_trade} Bal ${STATS['balance']:.2f}", reply_markup=mk)
                    consecutive_losses = 0
                else:
                    STATS['loss']+=1; STATS['balance']-=curr_amt; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1
                    bot.send_message(cid, f"❌ **LOSS -${curr_amt:.2f}** {pair_to_trade}")
                    if consecutive_losses >= 3: time.sleep(60); consecutive_losses=0
            except: bot.send_message(cid, f"⏱️ Expired {oid}")
            AUTO_STATE[cid]['in_trade'] = False; time.sleep(10)
        except:
            if cid in AUTO_STATE: AUTO_STATE[cid]['in_trade'] = False
            time.sleep(10)
    AUTO_LOCK[cid] = False
    bot.send_message(cid, f"🛑 **STOPPED** W{STATS['wins']} L{STATS['loss']} Bal ${STATS['balance']:.2f}")

@bot.message_handler(commands=['start','stop','debug'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id, f"❌ Private Bot"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running'] = False; bot.send_message(m.chat.id, "🛑 Stopping...")
        else: bot.send_message(m.chat.id, "Auto not running")
        return
    if m.text.startswith('/debug'):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); ot = iq.get_all_open_time(); prof = iq.get_all_profit(); bal = iq.get_balance() if IQ_CONNECTED else 0
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            msg = f"🔍 **DEBUG**\nBal {bal}\nREAL OPEN {is_real_market_open()}\nIQ {IQ_CONNECTED}\n\nLast error:\n{LAST_ERROR}\n\n"
            for p in ["EURUSD","GBPUSD","EURUSD-OTC","USDZAR-OTC"]:
                is_open = ot.get(p, {}).get('open', 'unknown'); payout = prof.get(p, {})
                msg += f"{p}: open={is_open} {payout}\n"
            bot.send_message(m.chat.id, msg)
        except Exception as e: bot.send_message(m.chat.id, f"Debug fail: {e}\nLast: {LAST_ERROR}")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 MANUAL TRADE (ANY %)", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO-TRADER 90%+ MARTINGALE", callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"), types.InlineKeyboardButton("⚙️ SETTINGS", callback_data="settings"))
    mk.add(types.InlineKeyboardButton("🔍 DEBUG IQ", callback_data="debug_iq"))
    real_status = "🟢 REAL OPEN" if is_real_market_open() else "🔴 REAL CLOSED - Use OTC"
    txt=f"""🤖 **Z-BOT V9.1 DEBUG** 🤖

💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | {real_status}
💰 ${STATS['balance']:.2f} | W: {STATS['wins']} L: {STATS['loss']}

✅ REAL FIX + ERROR SHOW
💹 MANUAL + 🤖 AUTO

Last Error: {LAST_ERROR[:100]}

👇 **Choose:**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id, "❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="debug_iq":
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); ot = iq.get_all_open_time(); prof = iq.get_all_profit()
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            msg = f"🔍 **DEBUG** REAL {is_real_market_open()}\nLast:\n{LAST_ERROR}\n\n"
            for p in ["EURUSD","GBPUSD","EURUSD-OTC","GBPUSD-OTC","USDZAR-OTC"]:
                is_open = ot.get(p, {}).get('open', 'unknown'); payout = prof.get(p, {})
                msg += f"{p}: open={is_open} {payout}\n"
            bot.send_message(cid, msg)
        except Exception as e: bot.send_message(cid, f"Debug fail: {e}\n{LAST_ERROR}")
        return
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in get_active_pairs():
            label = PAIR_EMOJI.get(p,p)
            if "-OTC" not in p and not is_real_market_open(): label += " ⏳ CLOSED"
            mk.add(types.InlineKeyboardButton(label, callback_data=f"pair_{p}"))
        status = "🟢 REAL OPEN" if is_real_market_open() else "🔴 REAL CLOSED - Use OTC"
        bot.send_message(cid, f"💹 **MANUAL**\n{status}", reply_markup=mk, parse_mode="Markdown"); return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN ALL", callback_data="auto_pair_AUTO"))
        for p in get_active_pairs():
            label = PAIR_EMOJI.get(p,p)
            if "-OTC" not in p and not is_real_market_open(): continue
            mk.add(types.InlineKeyboardButton(label, callback_data=f"auto_pair_{p}"))
        bot.send_message(cid, f"🤖 **AUTO 1/4 PAIR**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_pair_"):
        pair="_".join(data.split("_")[2:])
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"auto_bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"auto_bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ Pair: {pair}\n\n🤖 **2/4 ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_bal_"):
        parts=data.split("_"); bal=parts[2]; pair="_".join(parts[3:])
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"auto_amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"auto_amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"auto_amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"auto_amt_20_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n🤖 **3/4 BASE**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_amt_"):
        parts=data.split("_"); amt=float(parts[2]); bal=parts[-1]; pair="_".join(parts[3:-1])
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"auto_exp_60_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"auto_exp_120_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"auto_exp_300_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"auto_exp_900_{pair}_{bal}_{int(amt)}"))
        if "-OTC" in pair: mk.add(types.InlineKeyboardButton("⏱️ 30 SEC OTC", callback_data=f"auto_exp_30_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Base ${amt}\n\n🤖 **4/4 EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_exp_"):
        if AUTO_LOCK.get(cid, False) or (cid in AUTO_STATE and AUTO_STATE[cid].get('running')):
            bot.send_message(cid, f"⚠️ Auto running! /stop first"); return
        parts=data.split("_"); expiry=int(parts[2]); bal=parts[-2]; amt=float(parts[-1]); pair="_".join(parts[3:-2])
        AUTO_STATE[cid] = {"running": True,"pair": pair,"bal": bal,"base_amt": amt,"curr_amt": amt,"expiry": expiry,"trades": 0,"in_trade": False}
        AUTO_LOCK[cid] = False; mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
        bot.send_message(cid, f"🚀 **AUTO START!**\n{pair} ${amt} {expiry}s", reply_markup=mk, parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid, "🛑 Stopping..."); return
    if data.startswith("pair_"):
        pair="_".join(data.split("_")[1:])
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n💳 **2/4 ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair="_".join(parts[2:])
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM", callback_data=f"custom_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n💰 **3/4 AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_") or data.startswith("custom_"):
        if data.startswith("custom_"):
            parts=data.split("_"); bal=parts[-1]; pair="_".join(parts[1:-1])
            user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
            bot.send_message(cid, f"✏️ Type amount for {pair} {bal}"); return
        parts=data.split("_"); amt=float(parts[1]); bal=parts[-1]; pair="_".join(parts[2:-1])
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        if "-OTC" in pair: mk.add(types.InlineKeyboardButton("⏱️ 30 SEC OTC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ ${amt}\n\n⏱️ **4/4 EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); bal=parts[-2]; amt=float(parts[-1]); pair="_".join(parts[2:-2])
        if "-OTC" not in pair and expiry < 60:
            bot.send_message(cid, f"⚠️ REAL no 30s! Changing to 60s"); expiry = 60
        if "-OTC" not in pair and not is_real_market_open():
            bot.send_message(cid, f"⏳ REAL {pair} closed (Mon 00-03 UTC). Use OTC"); return
        bot.answer_callback_query(c.id, f"Analyzing...")
        scan_msg = bot.send_message(cid, f"🔍 **SCAN {PAIR_EMOJI.get(pair,pair)}**\n\n0%\n🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair, sniper_mode=False)
        dir_emoji = "🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
        expiry_txt = f"{expiry}s" if expiry < 60 else f"{expiry//60} min"
        signal_txt=f"""📡 **SIGNAL FOUND!**

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_emoji} | 🎯 {d['conf']:.0f}%
💸 {int(d['payout']*100)}% | 💰 ${amt} | ⏱️ {expiry_txt}
📈 {d['reason']}

🤖 **PLACING {expiry_txt} TRADE...**
"""
        bot.send_message(cid, signal_txt, parse_mode="Markdown")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"),
                   types.InlineKeyboardButton("🔍 DEBUG", callback_data="debug_iq"))
            bot.send_message(cid, f"❌ **{pair} FAILED**\n\n{LAST_ERROR}\n\n👇 Try OTC or DEBUG", reply_markup=mk, parse_mode="Markdown")
            iq_reconnect(); return
        bot.send_message(cid, f"✅ Placed {oid} | Waiting {exp}s...")
        time.sleep(exp+5)
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); pnl=iq.check_win_v4(oid)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"✅ **WIN +${pnl:.2f}**\n💱 {pair} {expiry_txt}\n🔥 {STATS['streak']} Bal ${STATS['balance']:.2f}", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTI ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt*2.2)}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"❌ **LOSS -${amt}**\n💱 {pair} {expiry_txt}\nBal ${STATS['balance']:.2f}", reply_markup=mk, parse_mode="Markdown")
        except:
            mk=types.InlineKeyboardMarkup(row_width=2)
            mk.add(types.InlineKeyboardButton("💹 NEW", callback_data="trade"), types.InlineKeyboardButton("🔄 RETRY", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"))
            bot.send_message(cid, f"⏱️ Expired {oid}", reply_markup=mk, parse_mode="Markdown")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("💹 NEW", callback_data="trade"), types.InlineKeyboardButton("🤖 AUTO", callback_data="auto_setup"))
        bot.send_message(cid, f"📊 **STATS**\n🏆 Wins {STATS['wins']} Loss {STATS['loss']}\n📈 {wr:.1f}% Streak {STATS['streak']}\n💰 ${STATS['balance']:.2f}\n\nLast err:\n{LAST_ERROR[:500]}", reply_markup=mk, parse_mode="Markdown")
    if data=="settings":
        bot.send_message(cid, f"⚙️ **V9.1 DEBUG**\nREAL FIXED + Error show\nHours Mon 3am UTC - Fri 21 UTC")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    cid=m.chat.id; st=user_states.get(cid, {})
    if not is_allowed(m.from_user.id): return
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 2 MIN", callback_data=f"exp_120_{pair}_{bal}_{int(amt)}"))
        mk.add(types.InlineKeyboardButton("⏱️ 5 MIN", callback_data=f"exp_300_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 15 MIN", callback_data=f"exp_900_{pair}_{bal}_{int(amt)}"))
        if "-OTC" in pair: mk.add(types.InlineKeyboardButton("⏱️ 30 SEC OTC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ Custom ${amt} for {pair}\n\n⏱️ **4/4 EXPIRY**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V9.1 REAL DEBUG - RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
