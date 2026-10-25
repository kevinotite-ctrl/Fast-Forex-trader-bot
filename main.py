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
    now=datetime.now(WAT)
    if now.weekday()>=5: return True
    return 18 <= now.hour <= 23

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

def get_iq_candles(pair, timeframe=60, count=100):
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
    if payout < 0.80: return None
    df = get_iq_candles(pair, 60, 100)
    if df is None or len(df)<50: return None
    try:
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi = calc_rsi(close, 7)
        rsi_now=float(rsi.iloc[-1]); price=float(close.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        last3_c = close.tail(3); last3_o = open_.tail(3)
        three_bull = all(last3_c.iloc[i] > last3_o.iloc[i] for i in range(3)) and last3_c.iloc[2] > last3_c.iloc[1]
        three_bear = all(last3_c.iloc[i] < last3_o.iloc[i] for i in range(3)) and last3_c.iloc[2] < last3_c.iloc[1]
        support=float(low.tail(20).min()); resist=float(high.tail(20).max())
        last_open=float(open_.iloc[-1]); last_close=float(close.iloc[-1])
        last_high=float(high.iloc[-1]); last_low=float(low.iloc[-1])
        body = abs(last_close-last_open)
        total_range = last_high-last_low
        if total_range==0: return None
        if body/total_range < 0.4: return None
        mom = (close.iloc[-1] - close.iloc[-3]) / close.iloc[-3] * 100
        if 'volume' in df.columns:
            vol_avg=float(df['volume'].tail(20).mean())
            vol_now=float(df['volume'].iloc[-1])
            if vol_now < vol_avg*0.6: return None

        sig=None; score=0; reason=""
        if price <= support*1.001 and rsi_now<35 and e9>e21 and three_bull and mom>0.01:
            sig="CALL"; score=91 + (35-rsi_now)*0.5; reason=f"RSI {rsi_now:.0f} Sweep LOW 3BULL {int(payout*100)}%"
        elif price >= resist*0.999 and rsi_now>65 and e9<e21 and three_bear and mom<-0.01:
            sig="PUT"; score=91 + (rsi_now-65)*0.5; reason=f"RSI {rsi_now:.0f} Sweep HIGH 3BEAR {int(payout*100)}%"
        elif rsi_now<26 and three_bull and e9>e21:
            sig="CALL"; score=88; reason=f"RSI {rsi_now:.0f} Oversold {int(payout*100)}%"
        elif rsi_now>74 and three_bear and e9<e21:
            sig="PUT"; score=88; reason=f"RSI {rsi_now:.0f} Overbought {int(payout*100)}%"
        elif rsi_now < 35 and e9>e21:
            sig="CALL"; score=82; reason=f"RSI {rsi_now:.0f} Bull {int(payout*100)}%"
        elif rsi_now > 65 and e9<e21:
            sig="PUT"; score=82; reason=f"RSI {rsi_now:.0f} Bear {int(payout*100)}%"

        if sig and score>=80:
            return {"pair":pair,"dir":sig,"conf":min(97,score),"price":price,"rsi":rsi_now,"df":df.tail(60),"sup":support,"res":resist,"reason":reason,"mom":mom,"payout":payout,"e9":e9,"e21":e21}
        return None
    except: return None

def scan_all_ready_pairs():
    ready=[]
    for p in OTC_PAIRS:
        sig = analyze_pair_for_ready(p)
        if sig: ready.append(sig)
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
    cap=f"{'🤖 AUTO' if auto else '📊'} {d['pair']} {d['dir']} {d['conf']:.0f}% {int(d['payout']*100)}% Payout\n{d['reason']}\nRSI7 {d['rsi']:.0f} Mom {d['mom']:.3f}%\nStake ${st} Exp 30s"
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{st}_PRACTICE"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{st}_PRACTICE"))
    try:
        plt.figure(figsize=(7,3)); plt.plot(d['df']['close'], color='gold'); plt.axhline(d['sup'], ls='--', c='green'); plt.axhline(d['res'], ls='--', c='red'); plt.title(f"{d['pair']} {d['dir']} {d['conf']:.0f}% {int(d['payout']*100)}%"); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(chat_id, open(p,'rb'), caption=cap, reply_markup=mk)
    except: bot.send_message(chat_id, cap, reply_markup=mk)
    STATS['last_trade']=datetime.now(WAT); STATS['signals_today']+=1

def send_trade_again(cid, bal_type="PRACTICE"):
    try:
        bot.send_message(cid, f"🔍 Finding next READY for {bal_type}...")
        time.sleep(2)
        ready = scan_all_ready_pairs()
        if not ready:
            mk=types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("🔄 Check READY Again", callback_data=f"refresh_ready_{bal_type}"))
            mk.add(types.InlineKeyboardButton("📊 SIGNAL NOW", callback_data="now"))
            bot.send_message(cid, "No pairs ready this second.\nTap Refresh to trade again", reply_markup=mk)
            return
        msg = f"🔁 **TRADE AGAIN? {len(ready)} READY:**\n({bal_type})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready[:6]:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}% {r['reason']}\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal_type}"))
        mk.add(types.InlineKeyboardButton("🔄 Refresh List", callback_data=f"refresh_ready_{bal_type}"), types.InlineKeyboardButton("⏸️ Stop Trading", callback_data="off"))
        bot.send_message(cid, msg, reply_markup=mk)
    except Exception as e:
        print(f"Trade again err {e}")

@bot.message_handler(commands=['start'])
def start(m):
    mk=types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("✅ READY PAIRS - Show Now", callback_data="ready_list"))
    mk.add(types.InlineKeyboardButton("💰 TRADE 30SEC (Ready Only)", callback_data="trade_flow"))
    mk.add(types.InlineKeyboardButton("▶️ AUTO ON Evening", callback_data="on"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="off"))
    mk.add(types.InlineKeyboardButton("📊 SIGNAL NOW", callback_data="now"), types.InlineKeyboardButton("📈 STATS", callback_data="stats"))
    iq_status = f"✅ {len(OTC_PAIRS)} OTC" if IQ_CONNECTED else "❌ Need IQ_EMAIL/PASS"
    bot.send_message(m.chat.id, f"V46.2 READY + AGAIN MODE\nIQ: {iq_status}\n18:00-23:59 WAT + Weekend\nPayout >=80% | Shows ONLY ready\nAfter result → Trade Again\nBal ${STATS['balance']:.1f} Daily ${STATS['daily']:.1f}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global AUTO_ON, AUTO_CHAT
    data=c.data; cid=c.message.chat.id
    
    if data=="ready_list":
        bot.answer_callback_query(c.id, "Scanning...")
        bot.send_message(cid, "🔍 Scanning 8 OTC for READY... 10 sec")
        ready = scan_all_ready_pairs()
        if not ready:
            bot.send_message(cid, "❌ No pairs ready now\n" + "\n".join([f"{p} {int(get_payout(p)*100)}%" for p in OTC_PAIRS]) + "\nTry in 20 sec")
            return
        msg = f"✅ **{len(ready)} PAIRS READY NOW:**\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% RSI {r['rsi']:.0f} {int(r['payout']*100)}% {r['reason']}\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_PRACTICE"))
        mk.add(types.InlineKeyboardButton("🔄 Refresh List", callback_data="ready_list"))
        bot.send_message(cid, msg, reply_markup=mk)
        return

    if data=="trade_flow":
        bot.answer_callback_query(c.id)
        user_states[cid]={"step":"choose_balance_for_ready"}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data="bal_ready_REAL"), types.InlineKeyboardButton("🟢 DEMO", callback_data="bal_ready_PRACTICE"))
        bot.send_message(cid, "💰 TRADE 30SEC Step 1/2: Choose account\nNext shows ONLY ready pairs (no waiting)", reply_markup=mk)
        return

    if data.startswith("bal_ready_"):
        bal=data.split("_")[2]
        bot.answer_callback_query(c.id, f"{bal} - Scanning...")
        bot.send_message(cid, f"✅ Account: {bal}\n🔍 Scanning for READY pairs only... 10 sec")
        ready = scan_all_ready_pairs()
        if not ready:
            bot.send_message(cid, "❌ No pairs ready now\nTap /start → READY to refresh")
            user_states.pop(cid,None)
            return
        msg = f"✅ **{len(ready)} READY - Choose to trade:**\n({bal})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}% {r['reason']}\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal}"))
        mk.add(types.InlineKeyboardButton("🔄 Refresh Ready List", callback_data=f"refresh_ready_{bal}"))
        user_states[cid]={"balance":bal,"step":"choose_ready_pair","ready_cache":ready}
        bot.send_message(cid, msg, reply_markup=mk)
        return

    if data.startswith("refresh_ready_"):
        bal=data.split("_")[2]
        bot.answer_callback_query(c.id, "Refreshing...")
        ready = scan_all_ready_pairs()
        if not ready:
            bot.send_message(cid, "❌ Still flat, try in 20 sec"); return
        msg = f"✅ **{len(ready)} READY (Refreshed):**\n({bal})\n\n"
        mk=types.InlineKeyboardMarkup(row_width=1)
        for r in ready:
            msg+=f"• {r['pair']} {r['dir']} {r['conf']:.0f}% {int(r['payout']*100)}%\n"
            mk.add(types.InlineKeyboardButton(f"▶️ {r['pair']} {r['dir']} {r['conf']:.0f}%", callback_data=f"trade_ready_{r['pair']}_{r['dir']}_{bal}"))
        mk.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_ready_{bal}"))
        bot.send_message(cid, msg, reply_markup=mk)
        return

    if data.startswith("trade_ready_"):
        parts=data.split("_")
        pair=parts[2]; dir_=parts[3]; bal=parts[4] if len(parts)>4 else "PRACTICE"
        bot.answer_callback_query(c.id, f"{pair} {dir_}")
        cache = user_states.get(cid, {}).get("ready_cache")
        found = next((x for x in cache if x['pair']==pair and x['dir']==dir_), None) if cache else None
        if not found: found = analyze_pair_for_ready(pair)
        if not found:
            bot.send_message(cid, f"{pair} not ready now, tap READY again"); return
        user_states[cid]={"balance":bal,"pair":pair,"dir":dir_,"conf_data":found,"step":"choose_amount_direct"}
        bot.send_message(cid, f"✅ **READY TO TRADE**\n{pair} {dir_} {found['conf']:.0f}% {int(found['payout']*100)}%\n{found['reason']}\nAccount: {bal}\n\n💵 Type amount (e.g 1, 1.5, 2)")
        return

    if data=="on":
        if not is_evening_otc_time(): bot.send_message(cid, f"😴 Sleeps until 18:00 WAT. Now {datetime.now(WAT).strftime('%H:%M')}"); return
        if not IQ_CONNECTED: bot.send_message(cid, "❌ IQ not connected. Set IQ_EMAIL and IQ_PASS in Render env"); return
        AUTO_ON=True; AUTO_CHAT=cid; bot.answer_callback_query(c.id,"Auto ON"); bot.send_message(cid,"✅ AUTO ON Evening OTC - Ready only")
    elif data=="off":
        AUTO_ON=False; bot.answer_callback_query(c.id,"Paused"); bot.send_message(cid, "⏸️ Auto Paused. Tap /start to trade manually")
    elif data=="stats":
        total=STATS['wins']+STATS['loss']; wr= (STATS['wins']/total*100) if total else 0
        pays = ", ".join([f"{p} {int(get_payout(p)*100)}%" for p in OTC_PAIRS[:4]])
        bot.send_message(cid, f"Stats V46.2: {STATS['wins']}W {STATS['loss']}L {wr:.0f}% WR\nDaily ${STATS['daily']:.2f} Marti {STATS['marti']} Stake ${stake()}\nPayouts: {pays}\nIQ: {IQ_CONNECTED}")
    elif data=="now":
        ready = scan_all_ready_pairs()
        if ready:
            for r in ready[:3]: send_sig(cid, r, auto=False)
        else:
            bot.send_message(cid, f"No ready pairs now")
    elif data.startswith("win_"):
        parts=data.split("_")
        st=float(parts[1]); bal_type=parts[2] if len(parts)>2 else "PRACTICE"
        pf=st*0.85; STATS['balance']+=pf; STATS['daily']+=pf; STATS['wins']+=1; STATS['marti']=0
        bot.answer_callback_query(c.id, "WIN logged")
        bot.send_message(cid,f"✅ WIN +${pf:.2f} Daily ${STATS['daily']:.2f}")
        send_trade_again(cid, bal_type)
    elif data.startswith("loss_"):
        parts=data.split("_")
        st=float(parts[1]); bal_type=parts[2] if len(parts)>2 else "PRACTICE"
        STATS['balance']-=st; STATS['daily']-=st; STATS['loss']+=1; STATS['marti']=min(3, STATS['marti']+1)
        bot.answer_callback_query(c.id, "LOSS logged")
        bot.send_message(cid,f"❌ LOSS -${st} Next ${stake()} Lvl{STATS['marti']+1}")
        send_trade_again(cid, bal_type)

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") in ["choose_amount","choose_amount_direct"])
def handle_amount(m):
    cid=m.chat.id
    try:
        amt=float(m.text.strip())
        if amt<1: bot.send_message(cid,"Min $1"); return
        st=user_states.get(cid, {})
        pair=st.get("pair"); bal=st.get("balance","PRACTICE"); dir_=st.get("dir")
        
        if st.get("step")=="choose_amount_direct":
            if not pair or not dir_:
                bot.send_message(cid,"Expired /start"); user_states.pop(cid,None); return
            if not IQ_CONNECTED:
                bot.send_message(cid, f"❌ IQ not connected"); user_states.pop(cid,None); return
            bot.send_message(cid, f"🤖 Placing {pair} {dir_} ${amt} on {bal}\nPayout {int(get_payout(pair)*100)}%")
            ok, oid, exp = iq_trade_30s(pair, dir_, amt, bal)
            if ok:
                bot.send_message(cid, f"🚀 PLACED ID {oid} Wait {exp}s")
                time.sleep(exp+5)
                try:
                    pnl = iq.check_win_v4(oid)
                    if pnl>0:
                        STATS['wins']+=1; STATS['daily']+=pnl; STATS['balance']+=pnl; STATS['marti']=0
                        bot.send_message(cid, f"✅ RESULT WIN +${pnl:.2f}\nDaily ${STATS['daily']:.2f} RESET")
                        time.sleep(1)
                        send_trade_again(cid, bal)
                    else:
                        STATS['loss']+=1; STATS['daily']-=amt; STATS['balance']-=amt; STATS['marti']=min(3, STATS['marti']+1)
                        bot.send_message(cid, f"❌ RESULT LOSS -${amt}\nNext ${stake()} Daily ${STATS['daily']:.2f}")
                        time.sleep(1)
                        send_trade_again(cid, bal)
                except:
                    bot.send_message(cid, f"⌛ Pending ID {oid} Check IQ. Use buttons below")
                    mk=types.InlineKeyboardMarkup(row_width=2)
                    mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{amt}_{bal}"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{amt}_{bal}"))
                    bot.send_message(cid, "Log result:", reply_markup=mk)
            else:
                bot.send_message(cid, "Auto fail, try manual")
                send_trade_again(cid, bal)
            user_states.pop(cid,None)
            return
    except Exception as e:
        bot.send_message(cid,f"Type number like 1 Error {e}")

def loop():
    while True:
        try:
            if AUTO_ON and AUTO_CHAT and (not STATS['last_trade'] or datetime.now(WAT)-STATS['last_trade']>=timedelta(minutes=2)):
                if not is_evening_otc_time(): time.sleep(300); continue
                ready = scan_all_ready_pairs()
                for r in ready[:2]:
                    send_sig(AUTO_CHAT, r, auto=True)
                    time.sleep(2)
            time.sleep(60)
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
    return "V46.2 READY + AGAIN RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
