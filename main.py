import os, time, threading, warnings
from datetime import datetime, timedelta
import pytz
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

WAT = pytz.timezone("Africa/Lagos")
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
STATS = {"balance":100.0,"daily":0.0,"wins":0,"loss":0,"marti":0,"last_trade":None,"signals_today":0}
AUTO_ON=False; AUTO_CHAT=None; BASE=float(os.getenv("TRADE_AMOUNT","1"))
user_states = {}

IQ_CONNECTED=False; iq=None
try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        iq=IQ_Option(EMAIL,PWD)
        check,reason=iq.connect()
        IQ_CONNECTED=iq.check_connect()
        print(f"IQ Connected: {IQ_CONNECTED}")
        if IQ_CONNECTED:
            try: iq.change_balance("PRACTICE")
            except: pass
except Exception as e:
    print(f"IQ Conn fail: {e}")
    IQ_CONNECTED=False

def is_evening_otc_time():
    return True

def get_payout(pair):
    if not IQ_CONNECTED: return 0.85
    try:
        all_profit = iq.get_all_profit()
        if pair in all_profit:
            p = all_profit[pair]
            for k in ['turbo','blitz','binary']:
                if k in p: return float(p[k])
        return iq.get_profit(pair) or 0.8
    except: return 0.8

def get_iq_candles(pair, timeframe=60, count=50): # 50 = faster
    if not IQ_CONNECTED: return None
    try:
        end = time.time()
        candles = iq.get_candles(pair, timeframe, count, end)
        if not candles or len(candles)<30: return None
        candles = sorted(candles, key=lambda x: x['from'])
        df = pd.DataFrame(candles)
        return df
    except: return None

def calc_rsi(closes, period=7):
    delta = closes.diff()
    gain = delta.where(delta>0,0).rolling(period).mean()
    loss = -delta.where(delta<0,0).rolling(period).mean()
    rs = gain/loss
    rsi = 100-(100/(1+rs))
    return rsi

def analyze_pair_for_ready(pair):
    payout = get_payout(pair)
    if payout < 0.70: return None
    df = get_iq_candles(pair, 60, 50)
    if df is None or len(df)<30: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi = calc_rsi(close, 7)
        rsi_now=float(rsi.iloc[-1]); rsi_prev=float(rsi.iloc[-2])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom_1 = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
        mom_3 = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] * 100
        last_close=float(close.iloc[-1]); last_open=float(open_.iloc[-1])
        is_green = last_close > last_open
        is_red = last_close < last_open
        sig=None; score=0; reason=""
        if mom_1 > 0.02 and mom_3 > 0.05 and is_green and e9 > e21 and rsi_now > 50 and rsi_now < 78 and rsi_now > rsi_prev:
            sig="CALL"; score=88 + (mom_3*80); reason=f"MOM BULL {mom_1:.3f}% {mom_3:.3f}% RSI {rsi_now:.0f} {int(payout*100)}%"
        elif mom_1 < -0.02 and mom_3 < -0.05 and is_red and e9 < e21 and rsi_now < 50 and rsi_now > 22 and rsi_now < rsi_prev:
            sig="PUT"; score=88 + abs(mom_3*80); reason=f"MOM BEAR {mom_1:.3f}% {mom_3:.3f}% RSI {rsi_now:.0f} {int(payout*100)}%"
        elif e9 > e21 and is_green and mom_1 > 0.01 and rsi_now > 55 and rsi_now < 70:
            sig="CALL"; score=84; reason=f"EMA BULL MOM {mom_1:.3f}% {int(payout*100)}%"
        elif e9 < e21 and is_red and mom_1 < -0.01 and rsi_now < 45 and rsi_now > 30:
            sig="PUT"; score=84; reason=f"EMA BEAR MOM {mom_1:.3f}% {int(payout*100)}%"
        elif rsi_now > 60 and rsi_now > rsi_prev and rsi_now < 75 and mom_3 > 0.03:
            sig="CALL"; score=80; reason=f"RSI PUSH UP {rsi_now:.0f} {int(payout*100)}%"
        elif rsi_now < 40 and rsi_now < rsi_prev and rsi_now > 25 and mom_3 < -0.03:
            sig="PUT"; score=80; reason=f"RSI PUSH DOWN {rsi_now:.0f} {int(payout*100)}%"
        elif mom_1 > 0.03 and is_green and rsi_now > 52:
            sig="CALL"; score=78; reason=f"FAST SCALP UP {mom_1:.3f}% {int(payout*100)}%"
        elif mom_1 < -0.03 and is_red and rsi_now < 48:
            sig="PUT"; score=78; reason=f"FAST SCALP DOWN {mom_1:.3f}% {int(payout*100)}%"

        if sig and score>=75:
            return {"pair":pair,"dir":sig,"conf":min(96,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"df":df.tail(40),"sup":float(close.tail(20).min()),"res":float(close.tail(20).max()),"reason":reason,"mom":mom_3,"payout":payout,"e9":e9,"e21":e21}
        return None
    except: return None

def scan_all_ready_pairs():
    # PARALLEL - 8 at once = 2-3 sec
    ready=[]
    def check_one(p):
        try: return analyze_pair_for_ready(p)
        except: return None
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_one, p): p for p in OTC_PAIRS}
        for f in as_completed(futures):
            res = f.result()
            if res: ready.append(res)
    return sorted(ready, key=lambda x: x['conf'], reverse=True)

def stake(): return round(BASE * (2.2 ** STATS['marti']),2)

def iq_trade_30s(pair, direction, amount, bal_type):
    try:
        iq.change_balance(bal_type)
        try:
            _, oid = iq.buy_blitz(pair, amount, direction.lower(), 30)
            return True, oid, 30
        except:
            _, oid = iq.buy(amount, pair, direction.lower(), 1)
            return True, oid, 60
    except Exception as e:
        print(f"Trade err {e}")
        return False, None, 0

def send_sig(chat_id, d, auto=False):
    st=stake()
    cap=f"{'🤖 AUTO' if auto else '⚡ MOM'} {d['pair']} {d['dir']} {d['conf']:.0f}% {int(d['payout']*100)}%\n{d['reason']}\nRSI {d['rsi']:.0f} MOM {d['mom']:.3f}%"
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{st}_PRACTICE"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{st}_PRACTICE"))
    try:
        plt.figure(figsize=(7,3)); plt.plot(d['df']['close'], color='gold'); plt.title(f"{d['pair']} {d['dir']} {d['conf']:.0f}%"); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(chat_id, open(p,'rb'), caption=cap, reply_markup=mk)
    except: bot.send_message(chat_id, cap, reply_markup=mk)
    STATS['last_trade']=datetime.now(WAT); STATS['signals_today']+=1

def send_trade_again(cid, bal_type="PRACTICE"):
    try:
        ready = scan_all_ready_pairs() # instant parallel
        if not ready:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("⚡ Scan Again (2 sec)", callback_data=f"refresh_ready_{bal_type}"))
            bot.send_message(cid, "No momentum now, tap to rescan 2 sec", reply_markup=mk)
            return
        msg = f"🔁 **TRADE AGAIN? {len(ready)} READY (2 sec scan):**\n({bal_type})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready[:6]:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {r['reason']}\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal_type}"))
        mk.add(types.InlineKeyboardButton("⚡ Refresh 2 sec", callback_data=f"refresh_ready_{bal_type}"), types.InlineKeyboardButton("⏸️ Stop", callback_data="off"))
        bot.send_message(cid, msg, reply_markup=mk)
    except Exception as e:
        print(f"Again err {e}")

@bot.message_handler(commands=['start'])
def start(m):
    mk=types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("⚡ MOMENTUM READY 2 SEC", callback_data="ready_list"))
    mk.add(types.InlineKeyboardButton("💰 TRADE 30SEC Instant", callback_data="trade_flow"))
    mk.add(types.InlineKeyboardButton("▶️ AUTO ON", callback_data="on"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="off"))
    mk.add(types.InlineKeyboardButton("📊 SIGNAL NOW", callback_data="now"), types.InlineKeyboardButton("📈 STATS", callback_data="stats"))
    iq_status = f"✅ {len(OTC_PAIRS)} OTC" if IQ_CONNECTED else "❌ Need IQ_EMAIL/PASS"
    bot.send_message(m.chat.id, f"V46.4 PARALLEL 2 SEC\nIQ: {iq_status}\n8 pairs parallel scan\nNo wait | Momentum instant\nAfter result → Trade Again\nBal ${STATS['balance']:.1f}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global AUTO_ON, AUTO_CHAT
    data=c.data; cid=c.message.chat.id
    if data=="ready_list":
        bot.answer_callback_query(c.id, "2 sec scan...")
        t0=time.time()
        ready = scan_all_ready_pairs()
        dt=time.time()-t0
        if not ready:
            bot.send_message(cid, f"❌ No momentum now ({dt:.1f}s scan)\nTap refresh in 10 sec")
            return
        msg = f"⚡ **{len(ready)} READY in {dt:.1f}s:**\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {r['reason']}\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_PRACTICE"))
        mk.add(types.InlineKeyboardButton(f"⚡ Refresh 2 sec", callback_data="ready_list"))
        bot.send_message(cid, msg, reply_markup=mk)
        return
    if data=="trade_flow":
        bot.answer_callback_query(c.id)
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data="bal_ready_REAL"), types.InlineKeyboardButton("🟢 DEMO", callback_data="bal_ready_PRACTICE"))
        bot.send_message(cid, "💰 Choose account - Next scan 2 sec", reply_markup=mk)
        return
    if data.startswith("bal_ready_"):
        bal=data.split("_")[2]
        bot.answer_callback_query(c.id, f"{bal} 2 sec...")
        t0=time.time()
        ready = scan_all_ready_pairs()
        dt=time.time()-t0
        if not ready:
            bot.send_message(cid, f"❌ No momentum now ({dt:.1f}s)\nTry again"); return
        msg = f"⚡ **{len(ready)} READY in {dt:.1f}s:**\n({bal})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}%\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal}"))
        mk.add(types.InlineKeyboardButton("⚡ Refresh 2 sec", callback_data=f"refresh_ready_{bal}"))
        user_states[cid]={"balance":bal,"ready_cache":ready}
        bot.send_message(cid, msg, reply_markup=mk)
        return
    if data.startswith("refresh_ready_"):
        bal=data.split("_")[2]
        bot.answer_callback_query(c.id, "2 sec...")
        ready = scan_all_ready_pairs()
        if not ready: bot.send_message(cid, "❌ No momentum"); return
        msg = f"⚡ **{len(ready)} READY:**\n({bal})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}%\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal}"))
        bot.send_message(cid, msg, reply_markup=mk)
        return
    if data.startswith("trade_ready_"):
        parts=data.split("_"); pair=parts[2]; dir_=parts[3]; bal=parts[4] if len(parts)>4 else "PRACTICE"
        bot.answer_callback_query(c.id, f"{pair} {dir_}")
        found = analyze_pair_for_ready(pair)
        if not found: bot.send_message(cid, f"{pair} momentum gone, refresh"); return
        user_states[cid]={"balance":bal,"pair":pair,"dir":dir_,"conf_data":found,"step":"choose_amount_direct"}
        bot.send_message(cid, f"✅ **INSTANT READY**\n{pair} {dir_} {found['conf']:.0f}% {int(found['payout']*100)}%\n{found['reason']}\nAccount: {bal}\n\n💵 Type amount (e.g 1)")
        return
    if data=="on":
        if not IQ_CONNECTED: bot.send_message(cid, "❌ IQ not connected"); return
        AUTO_ON=True; AUTO_CHAT=cid; bot.answer_callback_query(c.id,"Auto ON"); bot.send_message(cid,"✅ AUTO MOMENTUM 2 SEC ON")
    elif data=="off":
        AUTO_ON=False; bot.answer_callback_query(c.id,"Paused")
    elif data=="stats":
        total=STATS['wins']+STATS['loss']; wr= (STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"Stats V46.4: {STATS['wins']}W {STATS['loss']}L {wr:.0f}% WR\nDaily ${STATS['daily']:.2f} Marti {STATS['marti']}")
    elif data=="now":
        ready = scan_all_ready_pairs()
        if ready:
            for r in ready[:2]: send_sig(cid, r, auto=False)
        else: bot.send_message(cid, "No momentum now - 2 sec scan")
    elif data.startswith("win_"):
        parts=data.split("_"); st=float(parts[1]); bal_type=parts[2] if len(parts)>2 else "PRACTICE"
        pf=st*0.85; STATS['balance']+=pf; STATS['daily']+=pf; STATS['wins']+=1; STATS['marti']=0
        bot.answer_callback_query(c.id, "WIN"); bot.send_message(cid,f"✅ WIN +${pf:.2f} Daily ${STATS['daily']:.2f}"); send_trade_again(cid, bal_type)
    elif data.startswith("loss_"):
        parts=data.split("_"); st=float(parts[1]); bal_type=parts[2] if len(parts)>2 else "PRACTICE"
        STATS['balance']-=st; STATS['daily']-=st; STATS['loss']+=1; STATS['marti']=min(3, STATS['marti']+1)
        bot.answer_callback_query(c.id, "LOSS"); bot.send_message(cid,f"❌ LOSS -${st} Next ${stake()}"); send_trade_again(cid, bal_type)

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="choose_amount_direct")
def handle_amount(m):
    cid=m.chat.id
    try:
        amt=float(m.text.strip())
        if amt<1: bot.send_message(cid,"Min $1"); return
        st=user_states.get(cid, {}); pair=st.get("pair"); bal=st.get("balance","PRACTICE"); dir_=st.get("dir")
        if not pair: bot.send_message(cid,"Expired /start"); user_states.pop(cid,None); return
        bot.send_message(cid, f"🚀 {pair} {dir_} ${amt} {bal}")
        ok, oid, exp = iq_trade_30s(pair, dir_, amt, bal)
        if ok:
            bot.send_message(cid, f"🚀 PLACED {oid} Wait {exp}s")
            time.sleep(exp+5)
            try:
                pnl = iq.check_win_v4(oid)
                if pnl>0: STATS['wins']+=1; STATS['daily']+=pnl; STATS['balance']+=pnl; STATS['marti']=0; bot.send_message(cid, f"✅ WIN +${pnl:.2f}"); time.sleep(0.5); send_trade_again(cid, bal)
                else: STATS['loss']+=1; STATS['daily']-=amt; STATS['balance']-=amt; STATS['marti']=min(3, STATS['marti']+1); bot.send_message(cid, f"❌ LOSS -${amt}"); time.sleep(0.5); send_trade_again(cid, bal)
            except:
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{amt}_{bal}"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{amt}_{bal}"))
                bot.send_message(cid, "Log result:", reply_markup=mk)
        else: bot.send_message(cid, "Fail"); send_trade_again(cid, bal)
        user_states.pop(cid,None)
    except Exception as e: bot.send_message(cid,f"Type number Error {e}")

def loop():
    while True:
        try:
            if AUTO_ON and AUTO_CHAT and (not STATS['last_trade'] or datetime.now(WAT)-STATS['last_trade']>=timedelta(minutes=2)):
                ready = scan_all_ready_pairs()
                for r in ready[:2]: send_sig(AUTO_CHAT, r, auto=True); time.sleep(1)
            time.sleep(40)
        except: time.sleep(20)
threading.Thread(target=loop, daemon=True).start()

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V46.4 PARALLEL 2 SEC RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
