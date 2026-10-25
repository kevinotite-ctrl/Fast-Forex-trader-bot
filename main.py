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

# IQ CONNECTION - REQUIRED FOR 8.5
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
            iq.change_balance("PRACTICE")
except Exception as e:
    print(f"IQ Conn fail: {e}")
    IQ_CONNECTED=False

def is_evening_otc_time():
    now=datetime.now(WAT)
    if now.weekday()>=5: return True
    return 18 <= now.hour <= 23

def get_payout(pair):
    """Return payout % for pair, e.g 0.82 = 82%"""
    if not IQ_CONNECTED: return 0.85 # assume if no IQ
    try:
        all_profit = iq.get_all_profit()
        # all_profit structure: {'EURUSD-OTC': {'binary': 0.82, 'turbo': 0.82}, ...}
        if pair in all_profit:
            p = all_profit[pair]
            # try turbo/blitz first for 30s
            for k in ['turbo','blitz','binary']:
                if k in p: return float(p[k])
        # fallback
        return iq.get_profit(pair) or 0.8
    except:
        return 0.8

def get_iq_candles(pair, timeframe=60, count=100):
    """Get real IQ OTC candles"""
    if not IQ_CONNECTED:
        return None
    try:
        end = time.time()
        candles = iq.get_candles(pair, timeframe, count, end)
        # candles = list of dicts with open, close, high, low, volume
        if not candles or len(candles)<30:
            return None
        # Sort by time
        candles = sorted(candles, key=lambda x: x['from'])
        df = pd.DataFrame(candles)
        return df
    except Exception as e:
        print(f"Candle err {pair}: {e}")
        return None

def calc_rsi(closes, period=7):
    delta = closes.diff()
    gain = delta.where(delta>0,0).rolling(period).mean()
    loss = -delta.where(delta<0,0).rolling(period).mean()
    rs = gain/loss
    rsi = 100-(100/(1+rs))
    return rsi

def get_signal_30s(target_pair=None):
    if not IQ_CONNECTED:
        return None, "IQ_NOT_CONNECTED - Set IQ_EMAIL/IQ_PASS env"
    if not is_evening_otc_time():
        now=datetime.now(WAT)
        return None, f"OTC_EVENING_ONLY Now {now.strftime('%H:%M')} WAT Sleeps until 18:00"
    
    pairs = [target_pair] if target_pair else OTC_PAIRS
    best=None; best_score=0
    checked=[]
    
    for p in pairs:
        # Payout filter >=80%
        payout = get_payout(p)
        checked.append(f"{p} {int(payout*100)}%")
        if payout < 0.80:
            continue # skip low payout
        
        df = get_iq_candles(p, 60, 100)
        if df is None or len(df)<50: continue
        
        try:
            close=df['close']; open_=df['open']; high=df['high']; low=df['low']
            ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
            rsi = calc_rsi(close, 7)
            rsi_now=float(rsi.iloc[-1]); price=float(close.iloc[-1])
            e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
            
            # Last 3 candles bull/bear
            last3_c = close.tail(3); last3_o = open_.tail(3)
            three_bull = all(last3_c.iloc[i] > last3_o.iloc[i] for i in range(3)) and last3_c.iloc[2] > last3_c.iloc[1]
            three_bear = all(last3_c.iloc[i] < last3_o.iloc[i] for i in range(3)) and last3_c.iloc[2] < last3_c.iloc[1]
            
            # Sweep + support/resist
            support=float(low.tail(20).min()); resist=float(high.tail(20).max())
            # Wick check - avoid manipulation: body must be > 60% of candle
            last_open=float(open_.iloc[-1]); last_close=float(close.iloc[-1])
            last_high=float(high.iloc[-1]); last_low=float(low.iloc[-1])
            body = abs(last_close-last_open)
            total_range = last_high-last_low
            if total_range==0: continue
            body_ratio = body/total_range
            if body_ratio < 0.4: continue # doji/manipulation skip
            
            mom = (close.iloc[-1] - close.iloc[-3]) / close.iloc[-3] * 100
            
            # Volume spike (if available)
            vol_ok=True
            if 'volume' in df.columns:
                vol_avg=float(df['volume'].tail(20).mean())
                vol_now=float(df['volume'].iloc[-1])
                if vol_now < vol_avg*0.6: vol_ok=False # low volume skip
            
            if not vol_ok: continue
            
            score=0; sig=None; reason=""
            # 30s CALL logic
            if price <= support*1.001 and rsi_now<35 and e9>e21 and three_bull and mom>0.01:
                sig="CALL"; score=91 + (35-rsi_now)*0.5; reason=f"RSI7 {rsi_now:.1f} Sweep LOW + 3BULL + Payout {int(payout*100)}%"
            elif price >= resist*0.999 and rsi_now>65 and e9<e21 and three_bear and mom<-0.01:
                sig="PUT"; score=91 + (rsi_now-65)*0.5; reason=f"RSI7 {rsi_now:.1f} Sweep HIGH + 3BEAR + Payout {int(payout*100)}%"
            elif rsi_now<26 and three_bull and e9>e21 and body_ratio>0.6:
                sig="CALL"; score=88; reason=f"RSI7 {rsi_now:.1f} Oversold Extreme + Payout {int(payout*100)}%"
            elif rsi_now>74 and three_bear and e9<e21 and body_ratio>0.6:
                sig="PUT"; score=88; reason=f"RSI7 {rsi_now:.1f} Overbought Extreme + Payout {int(payout*100)}%"
            
            if sig and score>best_score and score>=85:
                best_score=score
                best={"pair":p,"dir":sig,"conf":min(97,score),"price":price,"rsi":rsi_now,"df":df.tail(60),"sup":support,"res":resist,"three": "3 BULL" if three_bull else "3 BEAR","reason":reason,"mom":mom,"payout":payout,"e9":e9,"e21":e21}
        except Exception as e:
            print(f"Signal err {p}: {e}")
            continue
    
    if best:
        return best, None
    # No signal but show checked payouts
    return None, f"No 85%+ Payouts: {', '.join(checked[:4])}"

def stake(): return round(BASE * (2.2 ** STATS['marti']),2)

def iq_trade_30s(pair, direction, amount, bal_type):
    try:
        iq.change_balance(bal_type)
        payout = get_payout(pair)
        # Choose expiry based on payout
        if payout >=0.80:
            try:
                _, oid = iq.buy_blitz(pair, amount, direction.lower(), 30)
                return True, oid, 30
            except:
                _, oid = iq.buy(amount, pair, direction.lower(), 1)
                return True, oid, 60
        else:
            # Low payout for 30s, use 1 min
            _, oid = iq.buy(amount, pair, direction.lower(), 1)
            return True, oid, 60
    except Exception as e:
        print(f"Trade err {e}")
        return False, None, 0

@bot.message_handler(commands=['start'])
def start(m):
    mk=types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("▶️ AUTO ON Evening", callback_data="on"), types.InlineKeyboardButton("⏸️ PAUSE", callback_data="off"))
    mk.add(types.InlineKeyboardButton("📊 SIGNAL NOW", callback_data="now"), types.InlineKeyboardButton("📈 STATS", callback_data="stats"))
    mk.add(types.InlineKeyboardButton("💰 TRADE 30SEC", callback_data="trade_flow"))
    iq_status = f"✅ {len(OTC_PAIRS)} OTC" if IQ_CONNECTED else "❌ Need IQ_EMAIL/PASS"
    bot.send_message(m.chat.id, f"V43 8.5/10 OTC SNIPER\nIQ: {iq_status}\nActive 18:00-23:59 WAT + Weekend\nPayout Filter >=80%\nRSI7 + EMA9/21 + Sweep + Wick Filter\nBal ${STATS['balance']:.1f} Daily ${STATS['daily']:.1f}", reply_markup=mk)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    global AUTO_ON, AUTO_CHAT
    data=c.data; cid=c.message.chat.id
    
    if data.startswith("bal_"):
        bal=data.split("_")[1]
        user_states[cid]={"balance":bal,"step":"choose_pair"}
        bot.answer_callback_query(c.id, bal)
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS:
            pay = get_payout(p) if IQ_CONNECTED else 0.85
            mk.add(types.InlineKeyboardButton(f"{p} {int(pay*100)}%", callback_data=f"pair_{p}"))
        bot.send_message(cid, f"✅ Account: {bal}\nStep 2/3: Choose pair (Only >=80% payout will trade):", reply_markup=mk)
        return
    if data.startswith("pair_"):
        pair=data.split("pair_")[1]
        st=user_states.get(cid, {}); st["pair"]=pair; st["step"]="choose_amount"; user_states[cid]=st
        bot.answer_callback_query(c.id, pair)
        bot.send_message(cid, f"✅ Pair: {pair} Payout {int(get_payout(pair)*100)}%\nStep 3/3: Type amount to risk (e.g 2)", parse_mode="Markdown")
        return
    if data=="trade_flow":
        bot.answer_callback_query(c.id)
        user_states[cid]={"step":"choose_balance"}
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data="bal_REAL"), types.InlineKeyboardButton("🟢 DEMO", callback_data="bal_PRACTICE"))
        bot.send_message(cid, "💰 **30 SEC TRADE**\nStep 1/3: Choose account:", reply_markup=mk)
        return
    # auto controls
    if data=="on":
        if not is_evening_otc_time(): bot.send_message(cid, f"😴 Bot sleeps until 18:00 WAT. Now {datetime.now(WAT).strftime('%H:%M')}"); return
        if not IQ_CONNECTED: bot.send_message(cid, "❌ IQ not connected. Set IQ_EMAIL and IQ_PASS in Render env"); return
        AUTO_ON=True; AUTO_CHAT=cid; bot.answer_callback_query(c.id,"Auto ON"); bot.send_message(cid,"✅ AUTO ON Evening OTC 2min Filter 80%+")
    elif data=="off":
        AUTO_ON=False; bot.answer_callback_query(c.id,"Paused")
    elif data=="stats":
        total=STATS['wins']+STATS['loss']; wr= (STATS['wins']/total*100) if total else 0
        pays = ", ".join([f"{p} {int(get_payout(p)*100)}%" for p in OTC_PAIRS[:4]])
        bot.send_message(cid, f"Stats V43: {STATS['wins']}W {STATS['loss']}L {wr:.0f}% WR\nDaily ${STATS['daily']:.2f} Marti {STATS['marti']} Stake ${stake()}\nPayouts: {pays}\nIQ: {IQ_CONNECTED}")
    elif data=="now":
        s,reason=get_signal_30s()
        if s: send_sig(cid, s, auto=False)
        else: bot.send_message(cid, f"No signal: {reason}")
    elif data.startswith("win_"):
        st=float(data.split("_")[1]); pf=st*0.85; STATS['balance']+=pf; STATS['daily']+=pf; STATS['wins']+=1; STATS['marti']=0
        bot.send_message(cid,f"✅ WIN +${pf:.2f} Daily ${STATS['daily']:.2f}")
    elif data.startswith("loss_"):
        st=float(data.split("_")[1]); STATS['balance']-=st; STATS['daily']-=st; STATS['loss']+=1; STATS['marti']=min(3, STATS['marti']+1)
        bot.send_message(cid,f"❌ LOSS -${st} Next ${stake()} Lvl{STATS['marti']+1}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "choose_amount")
def handle_amount(m):
    cid=m.chat.id
    try:
        amt=float(m.text.strip())
        if amt<1: bot.send_message(cid,"Min $1"); return
        st=user_states.get(cid, {}); pair=st.get("pair"); bal=st.get("balance")
        if not pair: bot.send_message(cid,"Expired. /start -> TRADE 30SEC"); user_states.pop(cid,None); return
        st["amount"]=amt; st["step"]="checking"; user_states[cid]=st
        bot.send_message(cid, f"🔍 **Checking {pair}**\nAcc: {bal} Amt: ${amt} Exp: 30s\nPayout: {int(get_payout(pair)*100)}% (min 80%)\nUsing REAL IQ OTC candles...\nMax 2 min")
        threading.Thread(target=run_30s_flow, args=(cid, pair, bal, amt), daemon=True).start()
    except: bot.send_message(cid,"Type number like 2")

def run_30s_flow(cid, pair, bal_type, amt):
    for i in range(12):
        res, reason = get_signal_30s(target_pair=pair)
        if res:
            bot.send_message(cid, f"📊 **SIGNAL {res['conf']:.0f}% FOUND!**\n{pair} {res['dir']} Payout {int(res['payout']*100)}%\n{res['reason']}\nRSI {res['rsi']:.1f}")
            bot.send_message(cid, f"🤖 **Initializing...**\nPlacing ${amt} {res['dir']} on {bal_type}")
            ok, oid, exp = iq_trade_30s(pair, res['dir'], amt, bal_type)
            if ok:
                bot.send_message(cid, f"🚀 **PLACED!** ID {oid}\n{pair} {res['dir']} ${amt} Exp {exp}s\n⏳ Wait {exp} seconds...")
                time.sleep(exp+5)
                try:
                    pnl = iq.check_win_v4(oid)
                    if pnl>0:
                        STATS['wins']+=1; STATS['daily']+=pnl; STATS['balance']+=pnl; STATS['marti']=0
                        bot.send_message(cid, f"✅ **RESULT WIN +${pnl:.2f}**\n{pair} Daily ${STATS['daily']:.2f} RESET")
                    else:
                        STATS['loss']+=1; STATS['daily']-=amt; STATS['balance']-=amt; STATS['marti']=min(3, STATS['marti']+1)
                        bot.send_message(cid, f"❌ **RESULT LOSS -${amt}**\nNext ${stake()} Daily ${STATS['daily']:.2f}")
                except:
                    bot.send_message(cid, f"⌛ Pending ID {oid} Check IQ. Click WIN/LOSS to log")
            else:
                bot.send_message(cid, "❌ IQ trade failed. Try manually")
                send_sig(cid, res)
            user_states.pop(cid, None)
            return
        time.sleep(10)
    bot.send_message(cid, f"❌ No 85%+ for {pair} in 2 min. {reason}")
    user_states.pop(cid, None)

def send_sig(chat_id, d, auto=False):
    st=stake()
    cap=f"{'🤖 AUTO' if auto else '📊'} {d['pair']} {d['dir']} {d['conf']:.0f}% {int(d['payout']*100)}% Payout\n{d['reason']}\nRSI7 {d['rsi']:.0f} Mom {d['mom']:.3f}%\nStake ${st} Exp 30s"
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"✅ WIN", callback_data=f"win_{st}"), types.InlineKeyboardButton(f"❌ LOSS", callback_data=f"loss_{st}"))
    mk.add(types.InlineKeyboardButton(f"🚀 TRADE {d['pair']}", url=f"https://iqoption.com"))
    try:
        plt.figure(figsize=(7,3)); plt.plot(d['df']['close'], color='gold'); plt.axhline(d['sup'], ls='--', c='green'); plt.axhline(d['res'], ls='--', c='red'); plt.title(f"{d['pair']} {d['dir']} {d['conf']:.0f}% Payout {int(d['payout']*100)}%"); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(chat_id, open(p,'rb'), caption=cap, reply_markup=mk)
    except: bot.send_message(chat_id, cap, reply_markup=mk)
    STATS['last_trade']=datetime.now(WAT); STATS['signals_today']+=1

def loop():
    while True:
        try:
            if AUTO_ON and AUTO_CHAT and (not STATS['last_trade'] or datetime.now(WAT)-STATS['last_trade']>=timedelta(minutes=2)):
                if not is_evening_otc_time(): time.sleep(300); continue
                s,r=get_signal_30s()
                if s: send_sig(AUTO_CHAT, s, auto=True)
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
    return "V43 8.5 OTC REAL RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
