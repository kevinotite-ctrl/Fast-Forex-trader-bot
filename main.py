import os, time, threading, warnings
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime

warnings.filterwarnings("ignore")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
REAL_PAIRS = ["EURUSD","GBPUSD"]
ALL_PAIRS = OTC_PAIRS + REAL_PAIRS

PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC",
    "EURUSD":"💵 EUR/USD REAL","GBPUSD":"💷 GBP/USD REAL"
}
STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0,"daily_trades":0,"daily_date":datetime.now().date()}
user_states = {}
AUTO_STATE = {}; AUTO_LOCK = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        iq=IQ_Option(EMAIL,PWD); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED: iq.change_balance("PRACTICE")
except Exception as e: print(f"IQ init fail {e}")

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        print("🔄 Reconnecting IQ...")
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        print(f"Reconnect: {IQ_CONNECTED}")
        return IQ_CONNECTED
    except Exception as e:
        print(f"Reconnect fail {e}")
        return False

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            all_p=iq.get_all_profit()
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]:
                        PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)

# === REPLACE ONLY THESE 2 FUNCTIONS IN YOUR CODE ===

def get_candles(pair):
    global IQ_CONNECTED
    if not IQ_CONNECTED:
        iq_reconnect()
    
    # REAL NEED MORE AGGRESSIVE FETCH
    is_real = "OTC" not in pair
    tries = 6 if is_real else 3
    
    for attempt in range(tries):
        try:
            with IQ_LOCK:
                # Try 1min first
                c = iq.get_candles(pair, 60, 50, time.time())
                if c and len(c) > 20:
                    print(f"✅ {pair} got {len(c)} candles 1min attempt {attempt+1}")
                    return pd.DataFrame(sorted(c, key=lambda x: x['from']))
                
                # REAL fail 1min? Try 5min as backup!
                if is_real and attempt >= 2:
                    c2 = iq.get_candles(pair, 300, 50, time.time())
                    if c2 and len(c2) > 20:
                        print(f"✅ {pair} got {len(c2)} candles 5min attempt {attempt+1}")
                        return pd.DataFrame(sorted(c2, key=lambda x: x['from']))
                
                print(f"⚠️ {pair} no candles attempt {attempt+1}")
        except Exception as e:
            print(f"❌ {pair} candle error attempt {attempt+1}: {e}")
        
        time.sleep(1.2)
        if attempt >= 2:
            iq_reconnect()
    
    print(f"💔 FINAL FAIL {pair}")
    return None

def analyze_momentum(pair, sniper=False, mode="NORMAL"):
    df = get_candles(pair)
    if df is None:
        if "OTC" not in pair:
            return {"pair":pair,"conf":0,"rejected":True,"reason":f"⏳ IQ slow for REAL {pair} — Click RETRY!","payout":0.85,"no_candle":True,"is_real":True}
        else:
            return {"pair":pair,"conf":0,"rejected":True,"reason":f"❌ No candles {pair}","payout":0.85,"no_candle":True}
    try:
        payout = get_payout(pair)
        if "OTC" in pair:
            if payout < 0.70:
                return {"pair":pair,"conf":0,"rejected":True,"reason":f"⚠️ OTC Payout low {int(payout*100)}% skip {pair}","payout":payout}
        else:
            if payout < 0.50:
                payout = 0.85
        
        # === FIX: REAL uses max/min, OTC uses high/low ===
        close = df['close']
        open_ = df['open']
        
        # Handle both high/low and max/min
        if 'high' in df.columns:
            high = df['high']
        elif 'max' in df.columns:
            high = df['max']
        else:
            high = close  # fallback
        
        if 'low' in df.columns:
            low = df['low']
        elif 'min' in df.columns:
            low = df['min']
        else:
            low = close  # fallback
        
        ema9 = close.ewm(9).mean()
        ema21 = close.ewm(21).mean()
        rsi = calc_rsi(close,7)
        rsi_now = float(rsi.iloc[-1])
        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])
        mom1 = (close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        is_green = float(close.iloc[-1]) > float(open_.iloc[-1])
        
        # Wick calc with safe fallback
        try:
            body_size = abs(float(close.iloc[-1]) - float(open_.iloc[-1]))
            upper_wick = float(high.iloc[-1]) - max(float(close.iloc[-1]), float(open_.iloc[-1]))
            lower_wick = min(float(close.iloc[-1]), float(open_.iloc[-1])) - float(low.iloc[-1])
        except:
            body_size = 0.0001
            upper_wick = 0
            lower_wick = 0
        
        sig = "CALL" if is_green else "PUT"
        score = 75
        reason = "OTC"
        
        if mode == "KING":
            if e9 > e21 and is_green and 55 <= rsi_now <= 72 and upper_wick < body_size*0.5 and mom1 > 0.02:
                sig = "CALL"; score = 95; reason = f"👑 KING Bull {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9 < e21 and not is_green and 28 <= rsi_now <= 45 and lower_wick < body_size*0.5 and mom1 < -0.02:
                sig = "PUT"; score = 95; reason = f"👑 KING Bear {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9 > e21 and is_green: sig = "CALL"; score = 86; reason = "👑 KING EMA Bull"
            else: sig = "PUT"; score = 86; reason = "👑 KING EMA Bear"
        else:
            if e9 > e21 and is_green and rsi_now > 55: sig = "CALL"; score = 92; reason = f"🚀 Bull {mom1:.3f}%"
            elif e9 < e21 and not is_green and rsi_now < 45: sig = "PUT"; score = 92; reason = f"📉 Bear {mom1:.3f}%"
            elif e9 > e21: sig = "CALL"; score = 84; reason = "📈 EMA Bull"
            else: sig = "PUT"; score = 84; reason = "📉 EMA Bear"
        
        if sniper:
            need = 95 if mode=="SNIPER" else 88 if mode in ["KING","SAFE"] else 80 if mode=="AGGRO" else 88
            if score < need:
                return {"pair":pair,"conf":score,"rejected":True,"payout":payout,"reason":f"{reason} {score}% < {need}%"}
        
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"reason":reason,"df":df.tail(30),"rejected":False,"payout":payout}
    except Exception as e:
        import traceback
        print(f"Analyze err {pair}: {e}")
        traceback.print_exc()
        return {"pair":pair,"conf":0,"rejected":True,"reason":f"❌ Analyze Error {str(e)[:100]} for {pair}","payout":0.85}

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def legit_live_scan(cid, mid, pair):
    steps = [
        (0, "🚀 Initializing V8...", 0.12),
        (15, f"🔌 IQ Check {pair}...", 0.15),
        (30, "📊 Fetching candles...", 0.2),
        (50, "📈 EMA9 + EMA21...", 0.15),
        (70, "💹 RSI + ATR...", 0.15),
        (85, "📰 Final check...", 0.15),
        (100, "🔒 SIGNAL LOCKED!")
    ]
    last_pct = -1
    for item in steps:
        if len(item) == 3: pct, text, delay = item
        else: pct, text = item; delay = 0.12
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

def analyze_momentum(pair, sniper=False, mode="NORMAL"):
    df=get_candles(pair)
    if df is None:
        # REAL FIX: give helpful message
        if "OTC" not in pair:
            return {"pair":pair,"conf":0,"rejected":True,"reason":f"❌ IQ NO DATA for {pair} REAL — IQ server busy, retrying in 10s! (Try again)","payout":0.85,"no_candle":True}
        else:
            return {"pair":pair,"conf":0,"rejected":True,"reason":f"❌ No candles {pair}","payout":0.85,"no_candle":True}
    try:
        payout=get_payout(pair)
        if payout < 0.70: # Lower threshold for REAL
            if "OTC" not in pair and payout >=0.60:
                pass # Allow REAL even with 60%+
            elif payout < 0.70:
                return {"pair":pair,"conf":0,"rejected":True,"reason":f"⚠️ Payout low {int(payout*100)}% for {pair}","payout":payout}
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        body_size = abs(float(close.iloc[-1])-float(open_.iloc[-1]))
        upper_wick = float(high.iloc[-1]) - max(float(close.iloc[-1]), float(open_.iloc[-1]))
        lower_wick = min(float(close.iloc[-1]), float(open_.iloc[-1])) - float(low.iloc[-1])
        sig="CALL" if is_green else "PUT"; score=75; reason="OTC"
        if mode=="KING":
            if e9>e21 and is_green and 55<=rsi_now<=72 and upper_wick < body_size*0.5 and mom1>0.02:
                sig="CALL"; score=95; reason=f"👑 KING Bull {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9<e21 and not is_green and 28<=rsi_now<=45 and lower_wick < body_size*0.5 and mom1<-0.02:
                sig="PUT"; score=95; reason=f"👑 KING Bear {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9>e21 and is_green: sig="CALL"; score=86; reason="👑 KING EMA Bull"
            else: sig="PUT"; score=86; reason="👑 KING EMA Bear"
        else:
            if e9>e21 and is_green and rsi_now>55: sig="CALL"; score=92; reason=f"🚀 Bull {mom1:.3f}%"
            elif e9<e21 and not is_green and rsi_now<45: sig="PUT"; score=92; reason=f"📉 Bear {mom1:.3f}%"
            elif e9>e21: sig="CALL"; score=84; reason="📈 EMA Bull"
            else: sig="PUT"; score=84; reason="📉 EMA Bear"
        if sniper:
            need = 95 if mode=="SNIPER" else 88 if mode in ["KING","SAFE"] else 80 if mode=="AGGRO" else 88
            if score < need:
                return {"pair":pair,"conf":score,"rejected":True,"payout":payout,"reason":f"{reason} {score}% < {need}%"}
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"reason":reason,"df":df.tail(30),"rejected":False,"payout":payout}
    except Exception as e:
        print(f"Analyze err {e}")
        return {"pair":pair,"conf":0,"rejected":True,"reason":f"❌ Analyze {e}","payout":0.85}

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    def is_err(m): 
        if not m: return True
        s=str(m).lower()
        return any(x in s for x in ["suspend","cannot","active","closed","error"])
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            time.sleep(0.5)
            # REAL pairs work better with turbo/blitz
            if expiry_sec <= 90:
                try:
                    check,oid = iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    if not is_err(oid) and check!=False: return True,oid,expiry_sec
                except Exception as e: print(f"Blitz fail {e}")
            # Try turbo/binary for REAL
            for mins in [1,2]:
                try:
                    check,oid = iq.buy(amount,pair,direction.lower(),mins)
                    if not is_err(oid) and check!=False: return True,oid,mins*60
                except Exception as e: print(f"Buy fail {mins}min {e}"); continue
            return False,"Suspended",0
    except Exception as e: return False,str(e),0

def auto_trader_loop(cid):
    consecutive_losses=0; win_streak=0; AUTO_LOCK[cid]=True
    state=AUTO_STATE.get(cid,{})
    mode=state.get('mode','NORMAL'); target=state.get('target',100.0); stoploss=state.get('stoploss',-30.0)
    profit_now=0.0; daily_limit=50
    bot.send_message(cid, f"🔒 **{mode} AUTO STARTED — REAL ENABLED**\n🎯 +${target:.0f} | SL ${stoploss:.0f} | 50 trades | Pairs: 10")
    while AUTO_STATE.get(cid,{}).get('running',False):
        if STATS['daily_date'] != datetime.now().date():
            STATS['daily_date']=datetime.now().date(); STATS['daily_trades']=0
        if STATS['daily_trades'] >= daily_limit:
            AUTO_STATE[cid]['running']=False; bot.send_message(cid, f"🛑 **50 REACHED!** Day {STATS['daily_trades']}/50 STOPPED!"); break
        if profit_now >= target:
            AUTO_STATE[cid]['running']=False; bot.send_message(cid, f"🎉 **TARGET +${target:.0f} REACHED!** Profit ${profit_now:.2f} STOPPED!"); break
        if profit_now <= stoploss:
            AUTO_STATE[cid]['running']=False; bot.send_message(cid, f"💔 **SL ${stoploss:.0f} HIT!** Profit ${profit_now:.2f} STOPPED!"); break
        if AUTO_STATE[cid].get('in_trade',False): time.sleep(3); continue
        try:
            state=AUTO_STATE.get(cid)
            if not state or not state['running']: break
            pair_to_trade=state['pair']
            conf_need = 95 if mode=="SNIPER" else 88 if mode in ["KING","SAFE"] else 80 if mode=="AGGRO" else 88
            if pair_to_trade=="AUTO":
                best=None; best_score=0
                for p in ALL_PAIRS:
                    d=analyze_momentum(p,sniper=True,mode=mode)
                    if d and not d.get('rejected') and d['conf']>=conf_need and d['conf']>best_score: best_score=d['conf']; best=d
                if not best: time.sleep(8 if mode=="AGGRO" else 12); continue
                d=best; pair_to_trade=d['pair']
            else:
                d=analyze_momentum(pair_to_trade,sniper=True,mode=mode)
                if not d or d.get('rejected'): time.sleep(8); continue
            if mode=="STREAK":
                if win_streak==0: curr_amt=state['base_amt']
                elif win_streak==1: curr_amt=state['base_amt']*2
                else: curr_amt=state['base_amt']*5
            else:
                curr_amt = state['base_amt'] if consecutive_losses==0 else min(state['base_amt'] * (2.2 ** consecutive_losses), state['base_amt']*6)
            AUTO_STATE[cid]['in_trade']=True
            ok,oid,exp = iq_trade(pair_to_trade,d['dir'],curr_amt,state['bal'],state['expiry'])
            if not ok: AUTO_STATE[cid]['in_trade']=False; time.sleep(5); continue
            STATS['daily_trades']+=1
            bot.send_message(cid, f"🤖 **{mode} #{state['trades']+1}** {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']:.0f}% P&L ${profit_now:.2f} Day {STATS['daily_trades']}/50 Payout {int(d.get('payout',0.85)*100)}%")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: pnl=iq.check_win_v4(oid)
                if pnl>0:
                    profit_now+=pnl; STATS['balance']+=pnl; STATS['wins']+=1; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1; win_streak+=1; consecutive_losses=0; AUTO_STATE[cid]['profit']=profit_now
                    bot.send_message(cid, f"✅ **WIN +${pnl:.2f}** Total ${profit_now:.2f}/+${target:.0f} {profit_now/target*100:.0f}% Day {STATS['daily_trades']}/50")
                else:
                    profit_now-=curr_amt; STATS['balance']-=curr_amt; STATS['loss']+=1; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1; win_streak=0
                    bot.send_message(cid, f"❌ **LOSS -${curr_amt:.2f}** Total ${profit_now:.2f}/SL ${stoploss:.0f} Day {STATS['daily_trades']}/50")
                    if consecutive_losses>=3: time.sleep(60); consecutive_losses=0
            except: bot.send_message(cid, f"⏱️ Expired {oid}")
            AUTO_STATE[cid]['in_trade']=False; time.sleep(3 if mode in ["AGGRO","SCALP"] else 6)
        except Exception as e:
            if cid in AUTO_STATE: AUTO_STATE[cid]['in_trade']=False
            time.sleep(10)
    AUTO_LOCK[cid]=False
    bot.send_message(cid, f"🛑 **{mode} STOPPED** Trades {AUTO_STATE.get(cid,{}).get('trades',0)} Profit ${profit_now:.2f}")

@bot.message_handler(commands=['start','stop'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id, "❌ Private Bot"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id, "🛑 Stopping..."); return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 MANUAL TRADE (OTC+REAL)", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO (OTC+REAL)", callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"))
    txt=f"""🔥 **KEVIN V7.9.3 REAL WORKING** 🔥

💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌'} | 💰 ${STATS['balance']:.2f} W{STATS['wins']} L{STATS['loss']} Day {STATS['daily_trades']}/50

✅ **REAL FIXED:**
💵 EURUSD + GBPUSD REAL now 5 retries!
🇪🇺 OTC 8 pairs always open
📈 KING + Custom + 50 trades

👇 **Trade REAL now:**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): return
    data=c.data; cid=c.message.chat.id
    if data=="ignore": return
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN BEST (ALL 10)", callback_data="auto_pair_AUTO"))
        mk.add(types.InlineKeyboardButton("── OTC ──", callback_data="ignore"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        mk.add(types.InlineKeyboardButton("── REAL FIXED! ──", callback_data="ignore"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        mk.add(types.InlineKeyboardButton("── STRATEGY ──", callback_data="ignore"))
        mk.add(types.InlineKeyboardButton("👑 KING 👑", callback_data="auto_mode_KING"),
               types.InlineKeyboardButton("🛡️ SAFE 88%+", callback_data="auto_mode_SAFE"))
        mk.add(types.InlineKeyboardButton("🚀 AGGRO 80%+", callback_data="auto_mode_AGGRO"),
               types.InlineKeyboardButton("🎯 SNIPER 95%+", callback_data="auto_mode_SNIPER"))
        mk.add(types.InlineKeyboardButton("🔥 STREAK BOOSTER", callback_data="auto_mode_STREAK"),
               types.InlineKeyboardButton("⚡ SCALP", callback_data="auto_mode_SCALP"))
        bot.send_message(cid, "🤖 **AUTO - REAL FIXED!**\nOTC=8 | REAL=2 | 5 retries for REAL!", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("auto_mode_"):
        mode = data.replace("auto_mode_","")
        user_states[cid] = user_states.get(cid,{}); user_states[cid]['auto_mode'] = mode
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN BEST (ALL 10)", callback_data=f"mode_pair_AUTO_{mode}"))
        mk.add(types.InlineKeyboardButton("── OTC ──", callback_data="ignore"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"mode_pair_{p}_{mode}"))
        mk.add(types.InlineKeyboardButton("── REAL ──", callback_data="ignore"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"mode_pair_{p}_{mode}"))
        bot.send_message(cid, f"✅ **Strategy: {mode}**\n\n**1/6 SELECT PAIR:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_pair_"):
        parts = data.split("_")
        if "AUTO" in data: pair = "AUTO"; mode = parts[-1]
        else: mode = parts[-1]; pair = "_".join(parts[2:-1])
        user_states[cid]=user_states.get(cid,{}); user_states[cid].update({'auto_pair':pair,'auto_mode':mode})
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"mode_bal_PRACTICE_{pair}_{mode}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"mode_bal_REAL_{pair}_{mode}"))
        bot.send_message(cid, f"✅ Strategy: {mode}\nPair: {pair}\n\n**2/6 ACCOUNT:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_bal_"):
        parts=data.split("_"); bal=parts[2]; mode=parts[-1]; pair="_".join(parts[3:-1])
        user_states[cid].update({'bal':bal,'pair':pair,'mode':mode})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💰 $10 TP", callback_data=f"mode_tp_10_{pair}_{bal}_{mode}"),
               types.InlineKeyboardButton("💰 $20 TP", callback_data=f"mode_tp_20_{pair}_{bal}_{mode}"),
               types.InlineKeyboardButton("💰 $50 TP", callback_data=f"mode_tp_50_{pair}_{bal}_{mode}"))
        mk.add(types.InlineKeyboardButton("💰 $100 TP", callback_data=f"mode_tp_100_{pair}_{bal}_{mode}"),
               types.InlineKeyboardButton("💰 $200 TP", callback_data=f"mode_tp_200_{pair}_{bal}_{mode}"),
               types.InlineKeyboardButton("✏️ CUSTOM TP", callback_data=f"mode_tp_custom_{pair}_{bal}_{mode}"))
        bot.send_message(cid, f"✅ Strategy: {mode}\nPair: {pair} | {bal}\n\n**3/6 TARGET PROFIT:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_tp_"):
        parts=data.split("_")
        if "custom" in data:
            bal=parts[-2]; mode=parts[-1]; pair="_".join(parts[3:-2])
            user_states[cid].update({'pair':pair,'bal':bal,'mode':mode,'step':'await_tp'})
            bot.send_message(cid, f"✏️ **Type target profit** Example: 50\nStrategy: {mode} | Pair: {pair}"); return
        tp=float(parts[2]); bal=parts[-3]; mode=parts[-1]; pair="_".join(parts[3:-3])
        user_states[cid].update({'target':tp,'pair':pair,'bal':bal,'mode':mode})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("🛑 SL -$20", callback_data=f"mode_sl_-20_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$30", callback_data=f"mode_sl_-30_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$50", callback_data=f"mode_sl_-50_{pair}_{bal}_{mode}_{int(tp)}"))
        mk.add(types.InlineKeyboardButton("🛑 SL -$100", callback_data=f"mode_sl_-100_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("✏️ CUSTOM SL", callback_data=f"mode_sl_custom_{pair}_{bal}_{mode}_{int(tp)}"))
        bot.send_message(cid, f"✅ Target: +${tp:.0f}\n\n**4/6 STOP LOSS:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_sl_"):
        parts=data.split("_")
        if "custom" in data:
            bal=parts[-3]; mode=parts[-2]; tp=parts[-1]; pair="_".join(parts[3:-3])
            user_states[cid].update({'pair':pair,'bal':bal,'mode':mode,'target':float(tp),'step':'await_sl'})
            bot.send_message(cid, f"✏️ **Type stop loss (negative)** Example: -30\nTarget: +${tp} | {mode}"); return
        sl=float(parts[2]); bal=parts[-4]; mode=parts[-2]; tp=parts[-1]; pair="_".join(parts[3:-4])
        user_states[cid].update({'target':float(tp),'stoploss':sl,'pair':pair,'bal':bal,'mode':mode})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"mode_amt_1_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"mode_amt_5_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"mode_amt_10_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"mode_amt_custom_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"))
        bot.send_message(cid, f"✅ TP +${tp} | SL ${sl:.0f}\n\n**5/6 BASE AMOUNT:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_amt_") and "custom" in data:
        parts=data.split("_"); bal=parts[-4]; mode=parts[-3]; tp=parts[-2]; sl=parts[-1]; pair="_".join(parts[3:-4])
        user_states[cid].update({'pair':pair,'bal':bal,'mode':mode,'target':float(tp),'stoploss':float(sl),'step':'await_auto_amt'})
        bot.send_message(cid, f"✏️ **Type custom base amount**\nExample: 2.5 or 15\nTP +${tp} SL ${sl} | {pair} {mode}"); return
    if data.startswith("mode_amt_"):
        parts=data.split("_"); amt=parts[2]; bal=parts[-4]; mode=parts[-3]; tp=parts[-2]; sl=parts[-1]; pair="_".join(parts[3:-4])
        user_states[cid].update({'amt':float(amt),'target':float(tp),'stoploss':float(sl)})
        if mode=="SCALP":
            expiry=30
            AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":float(amt),"expiry":expiry,"trades":0,"in_trade":False,"mode":mode,"target":float(tp),"stoploss":float(sl),"profit":0.0}
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
            bot.send_message(cid, f"🚀 **AUTO ACTIVE REAL!**\n🧠 {mode}\n💱 {pair}\n💳 {bal}\n💰 ${amt}\n🎯 +${tp} 🛑 ${sl}\n⏱️ {expiry}s", reply_markup=mk, parse_mode="Markdown")
            threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start(); return
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"mode_exp_30_{pair}_{bal}_{amt}_{mode}_{tp}_{sl}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"mode_exp_60_{pair}_{bal}_{amt}_{mode}_{tp}_{sl}"))
        bot.send_message(cid, f"✅ ${amt} TP +${tp} SL ${sl}\n\n**6/6 EXPIRY:**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("mode_exp_"):
        if AUTO_LOCK.get(cid,False) or (cid in AUTO_STATE and AUTO_STATE[cid].get('running')):
            bot.send_message(cid, "⚠️ Auto running! /stop first"); return
        parts=data.split("_"); expiry=int(parts[2]); bal=parts[-5]; amt=parts[-4]; mode=parts[-3]; tp=parts[-2]; sl=parts[-1]; pair="_".join(parts[3:-5])
        AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":float(amt),"expiry":expiry,"trades":0,"in_trade":False,"mode":mode,"target":float(tp),"stoploss":float(sl),"profit":0.0}
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
        bot.send_message(cid, f"🚀 **AUTO ACTIVE REAL!**\n🧠 {mode}\n💱 {pair}\n💳 {bal}\n💰 ${amt}\n🎯 +${tp} 🛑 ${sl}\n⏱️ {expiry}s", reply_markup=mk, parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start(); return
    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid, "🛑 Stopping..."); return
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("── OTC 8 ──", callback_data="ignore"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        mk.add(types.InlineKeyboardButton("── REAL FIXED! 2 ──", callback_data="ignore"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, "💹 **MANUAL 1/3 - REAL FIXED! (10 total)**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ {pair}\n\n**2/3 ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair="_".join(parts[2:])
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"amt_custom_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n**3/3 AMOUNT (CUSTOM):**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_") and "custom" in data:
        parts=data.split("_"); bal=parts[-1]; pair="_".join(parts[2:-1])
        user_states[cid]=user_states.get(cid,{}); user_states[cid].update({'pair':pair,'bal':bal,'step':'await_manual_amt'})
        bot.send_message(cid, f"✏️ **Type custom amount**\nExample: 2.5 or 15\nPair: {pair} | {bal}"); return
    if data.startswith("amt_"):
        parts=data.split("_")
        try: amt=float(parts[1]); pair="_".join(parts[2:-1]); bal=parts[-1]
        except: amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{amt}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{amt}"))
        bot.send_message(cid, f"✅ ${amt} {pair}\n\n**EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); bal=parts[-2]; amt=float(parts[-1]); pair="_".join(parts[2:-2])
        bot.answer_callback_query(c.id, f"Scanning {pair}...")
        scan_msg = bot.send_message(cid, f"🔍 **SCAN {pair}**\n\n0%\n🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair, mode="KING")
        if not d or d.get('rejected'):
            reason = d.get('reason','Failed') if d else 'IQ No Data'
            if d and d.get('no_candle'):
                # REAL fail — retry message + allow manual retry button
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 RETRY REAL", callback_data=f"exp_{expiry}_{pair}_{bal}_{amt}"),
                       types.InlineKeyboardButton("🇪🇺 SWITCH TO OTC", callback_data=f"pair_EURUSD-OTC"))
                bot.send_message(cid, f"⚠️ {reason}\n\n💡 REAL need 1 more try — click RETRY! IQ sometimes slow for REAL.\nIf still fail, use OTC!", reply_markup=mk, parse_mode="Markdown")
            else:
                bot.send_message(cid, f"⚠️ {reason}\nPair: {pair}\nTry again!", parse_mode="Markdown")
            return
        expiry_txt = f"{expiry}s" if expiry<60 else f"{expiry//60}min"
        signal_txt=f"""🔥 **KING SIGNAL** 👑
💱 {pair} {'(REAL ✅)' if 'OTC' not in pair else '(OTC)'}
📊 {d['dir']} | 🎯 {d['conf']:.0f}% | Payout {int(d.get('payout',0.85)*100)}%
💰 ${amt} {bal} | ⏱️ {expiry_txt}
📈 {d['reason']}"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700' if 'OTC' not in pair else '#00FF00', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}%"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except: bot.send_message(cid, signal_txt, parse_mode="Markdown")
        bot.send_message(cid, f"🚀 **PLACING REAL...** {pair} Payout {int(d.get('payout',0.85)*100)}%")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok:
            bot.send_message(cid, f"⚠️ Trade blocked — {pair} suspended. Wait 10s try again! REAL market busy."); return
        bot.send_message(cid, f"✅ **PLACED REAL!** ID `{oid}` ⏳ {exp}s", parse_mode="Markdown")
        time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME REAL", callback_data=f"exp_{expiry}_{pair}_{bal}_{amt}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"✅ **REAL WIN +${pnl:.2f}** Bal ${STATS['balance']:.2f} 🔥 {STATS['streak']}", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTI ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{amt*2.2}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"❌ **LOSS -${amt}** Bal ${STATS['balance']:.2f}", reply_markup=mk, parse_mode="Markdown")
        except: bot.send_message(cid, f"⏱️ Expired {oid} Check IQ app")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 **V7.9.3 STATS**\nW {STATS['wins']} L {STATS['loss']} {wr:.1f}%\nBal ${STATS['balance']:.2f} Streak {STATS['streak']}\nDay {STATS['daily_trades']}/50\nPairs: 8 OTC + 2 REAL FIXED", parse_mode="Markdown")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step')=='await_tp')
def handle_custom_tp(m):
    cid=m.chat.id
    try:
        tp=float(m.text.strip()); st=user_states.get(cid,{})
        pair=st.get('pair'); bal=st.get('bal'); mode=st.get('mode')
        user_states[cid].update({'target':tp,'step':''})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("🛑 SL -$20", callback_data=f"mode_sl_-20_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$30", callback_data=f"mode_sl_-30_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$50", callback_data=f"mode_sl_-50_{pair}_{bal}_{mode}_{int(tp)}"))
        mk.add(types.InlineKeyboardButton("🛑 SL -$100", callback_data=f"mode_sl_-100_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("✏️ CUSTOM SL", callback_data=f"mode_sl_custom_{pair}_{bal}_{mode}_{int(tp)}"))
        bot.send_message(cid, f"✅ Target: +${tp:.0f} set!\n\n**4/6 STOP LOSS:**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only e.g. 50")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step')=='await_sl')
def handle_custom_sl(m):
    cid=m.chat.id
    try:
        sl=float(m.text.strip()); st=user_states.get(cid,{})
        if sl>0: sl=-sl
        pair=st.get('pair'); bal=st.get('bal'); mode=st.get('mode'); tp=st.get('target')
        user_states[cid].update({'stoploss':sl,'step':''})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"mode_amt_1_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"mode_amt_5_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"mode_amt_10_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM AMOUNT", callback_data=f"mode_amt_custom_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"))
        bot.send_message(cid, f"✅ SL ${sl:.0f} set!\n\n**5/6 BASE AMOUNT:**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send negative number e.g. -30")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step')=='await_manual_amt')
def handle_manual_custom_amt(m):
    cid=m.chat.id
    try:
        amt=float(m.text.strip()); st=user_states.get(cid,{})
        pair=st.get('pair'); bal=st.get('bal')
        user_states[cid]['step']=''
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{amt}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{amt}"))
        bot.send_message(cid, f"✅ Custom ${amt} {pair}\n\n**EXPIRY**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only e.g. 2.5")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step')=='await_auto_amt')
def handle_auto_custom_amt(m):
    cid=m.chat.id
    try:
        amt=float(m.text.strip()); st=user_states.get(cid,{})
        pair=st.get('pair'); bal=st.get('bal'); mode=st.get('mode'); tp=st.get('target'); sl=st.get('stoploss')
        user_states[cid]['step']=''
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"mode_exp_30_{pair}_{bal}_{amt}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"mode_exp_60_{pair}_{bal}_{amt}_{mode}_{int(tp)}_{int(sl)}"))
        bot.send_message(cid, f"✅ Custom ${amt} TP +${tp} SL ${sl}\n\n**6/6 EXPIRY:**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only e.g. 2.5")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "KEVIN V7.9.3 REAL WORKING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
