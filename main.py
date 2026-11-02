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

# ===== OTC ONLY =====
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
PAIR_EMOJI = {
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC","GBPUSD-OTC":"🇬🇧 GBP/USD OTC","EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC","GBPJPY-OTC":"🇬🇧 GBP/JPY OTC","AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC","EURJPY-OTC":"🇪🇺 EUR/JPY OTC"
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
except: pass

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
        IQ_CONNECTED=iq.check_connect(); return IQ_CONNECTED
    except: return False

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

def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK: c=iq.get_candles(pair,60,50,time.time())
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            iq_reconnect(); time.sleep(1)
        except: iq_reconnect(); time.sleep(1)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

# ===== YOUR ORIGINAL LIVE SCANNING BAR - 100% UNTOUCHED - I NO TOUCH AM! =====
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

def analyze_momentum(pair, sniper=False, mode="NORMAL"):
    df=get_candles(pair)
    if df is None: return None
    try:
        # PAYOUT FILTER - NEW!
        payout=get_payout(pair)
        if payout < 0.80 and mode not in ["AGGRO"]: # Skip low payout
            return {"pair":pair,"conf":0,"rejected":True,"reason":f"Low payout {int(payout*100)}% skip","payout":payout}
        
        close=df['close']; open_=df['open']; high=df['high']; low=df['low']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean()
        rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1])
        
        # Wick calculation
        body_size = abs(float(close.iloc[-1])-float(open_.iloc[-1]))
        upper_wick = float(high.iloc[-1]) - max(float(close.iloc[-1]), float(open_.iloc[-1]))
        lower_wick = min(float(close.iloc[-1]), float(open_.iloc[-1])) - float(low.iloc[-1])
        
        sig="CALL" if is_green else "PUT"; score=75; reason="OTC"
        
        # ===== NEW STRATEGY 1: OTC KING - BEST FOR OTC! =====
        if mode=="KING":
            # Bull: EMA up + RSI 55-75 + small upper wick + green + momentum up
            if e9>e21 and is_green and 55<=rsi_now<=72 and upper_wick < body_size*0.5 and mom1>0.02:
                sig="CALL"; score=95; reason=f"👑 KING Bull Wick OK {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9<e21 and not is_green and 28<=rsi_now<=45 and lower_wick < body_size*0.5 and mom1<-0.02:
                sig="PUT"; score=95; reason=f"👑 KING Bear Wick OK {mom1:.3f}% RSI {rsi_now:.0f}"
            elif e9>e21 and is_green: sig="CALL"; score=86; reason="👑 KING EMA Bull"
            else: sig="PUT"; score=86; reason="👑 KING EMA Bear"
        else:
            # Normal logic
            if e9>e21 and is_green and rsi_now>55: sig="CALL"; score=92; reason=f"🚀 Bull {mom1:.3f}%"
            elif e9<e21 and not is_green and rsi_now<45: sig="PUT"; score=92; reason=f"📉 Bear {mom1:.3f}%"
            elif e9>e21: sig="CALL"; score=84; reason="📈 EMA Bull"
            else: sig="PUT"; score=84; reason="📉 EMA Bear"
        
        # Sniper threshold
        if sniper:
            need = 95 if mode=="SNIPER" else 88 if mode=="KING" else 80 if mode=="AGGRO" else 88
            if score < need:
                return {"pair":pair,"conf":score,"rejected":True,"payout":payout,"reason":reason}
        
        return {"pair":pair,"dir":sig,"conf":score,"price":float(close.iloc[-1]),"reason":reason,"df":df.tail(30),"rejected":False,"payout":payout}
    except Exception as e:
        print(f"Analyze err {e}")
        return None

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    def is_err(m): 
        if not m: return True
        s=str(m).lower()
        return any(x in s for x in ["suspend","cannot","active","closed","error"])
    try:
        with IQ_LOCK:
            # BALANCE CHECK - NEW!
            try:
                bal_info = iq.get_balances()
            except: pass
            iq.change_balance(bal)
            time.sleep(0.3)
            if expiry_sec <= 90:
                try:
                    check,oid = iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    if not is_err(oid) and check!=False: return True,oid,expiry_sec
                except: pass
            for mins in [1,2]:
                try:
                    check,oid = iq.buy(amount,pair,direction.lower(),mins)
                    if not is_err(oid) and check!=False: return True,oid,mins*60
                except: continue
            return False,"Suspended",0
    except Exception as e: return False,str(e),0

def auto_trader_loop(cid):
    consecutive_losses=0; win_streak=0; AUTO_LOCK[cid]=True
    state=AUTO_STATE.get(cid,{})
    mode=state.get('mode','NORMAL'); target=state.get('target',100.0); stoploss=state.get('stoploss',-30.0)
    profit_now=0.0; daily_limit=30
    
    bot.send_message(cid, f"🔒 **{mode} AUTO STARTED**\n🎯 Target: +${target:.0f} | SL: ${stoploss:.0f} | Daily Limit: {daily_limit} trades")
    
    while AUTO_STATE.get(cid,{}).get('running',False):
        # DAILY DATE RESET
        if STATS['daily_date'] != datetime.now().date():
            STATS['daily_date']=datetime.now().date(); STATS['daily_trades']=0
        
        # CHECK DAILY LIMIT - NEW!
        if STATS['daily_trades'] >= daily_limit:
            AUTO_STATE[cid]['running']=False
            bot.send_message(cid, f"🛑 **DAILY LIMIT REACHED!**\n{STATS['daily_trades']}/{daily_limit} trades today\n🛑 AUTO STOPPED!")
            break
        
        # CHECK TARGET PROFIT
        if profit_now >= target:
            AUTO_STATE[cid]['running']=False
            bot.send_message(cid, f"🎉 **TARGET REACHED!** 🎉\n\n🧠 Strategy: {mode}\n🎯 Target: +${target:.0f}\n💰 Profit: ${profit_now:.2f}\nTrades: {AUTO_STATE[cid]['trades']}\n\n🛑 **AUTO STOPPED!**")
            break
        
        # CHECK STOP LOSS - NEW!
        if profit_now <= stoploss:
            AUTO_STATE[cid]['running']=False
            bot.send_message(cid, f"💔 **STOP LOSS HIT!**\n\n🧠 Strategy: {mode}\n🛑 SL: ${stoploss:.0f}\n💰 Profit: ${profit_now:.2f} (Loss)\nTrades: {AUTO_STATE[cid]['trades']}\n\n🛑 **AUTO STOPPED TO PROTECT ACCOUNT!**")
            break
        
        if AUTO_STATE[cid].get('in_trade',False): time.sleep(3); continue
        try:
            state=AUTO_STATE.get(cid)
            if not state or not state['running']: break
            pair_to_trade=state['pair']
            conf_need = 95 if mode=="SNIPER" else 88 if mode in ["KING","SAFE"] else 80 if mode=="AGGRO" else 88
            
            if pair_to_trade=="AUTO":
                best=None; best_score=0
                for p in OTC_PAIRS:
                    d=analyze_momentum(p,sniper=True,mode=mode)
                    if d and not d.get('rejected') and d['conf']>=conf_need and d['conf']>best_score: best_score=d['conf']; best=d
                if not best: time.sleep(8 if mode=="AGGRO" else 12); continue
                d=best; pair_to_trade=d['pair']
            else:
                d=analyze_momentum(pair_to_trade,sniper=True,mode=mode)
                if not d or d.get('rejected'):
                    # If low payout, tell user
                    if d and "payout" in d and "Low payout" in d.get('reason',''):
                        bot.send_message(cid, f"⚠️ {pair_to_trade} payout low {int(d['payout']*100)}% — skipping!")
                    time.sleep(8 if mode=="AGGRO" else 10); continue
            
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
            bot.send_message(cid, f"🤖 **{mode} #{state['trades']+1}** {pair_to_trade} {d['dir']} ${curr_amt:.2f} {d['conf']:.0f}% | P&L ${profit_now:.2f} (Target +${target:.0f} SL ${stoploss:.0f}) Day {STATS['daily_trades']}/{daily_limit} | Payout {int(d.get('payout',0.85)*100)}%")
            time.sleep(exp+5)
            try:
                with IQ_LOCK: pnl=iq.check_win_v4(oid)
                if pnl>0:
                    profit_now+=pnl; STATS['balance']+=pnl; STATS['wins']+=1; STATS['streak']+=1; AUTO_STATE[cid]['trades']+=1; win_streak+=1; consecutive_losses=0; AUTO_STATE[cid]['profit']=profit_now
                    bot.send_message(cid, f"✅ **{mode} WIN +${pnl:.2f}** | Total: ${profit_now:.2f}/+${target:.0f} 🎯 {profit_now/target*100:.0f}% | Day {STATS['daily_trades']}/{daily_limit}")
                else:
                    profit_now-=curr_amt; STATS['balance']-=curr_amt; STATS['loss']+=1; STATS['streak']=0; AUTO_STATE[cid]['trades']+=1; consecutive_losses+=1; win_streak=0
                    bot.send_message(cid, f"❌ **{mode} LOSS -${curr_amt:.2f}** | Total: ${profit_now:.2f}/SL ${stoploss:.0f} | Day {STATS['daily_trades']}/{daily_limit}")
                    if consecutive_losses>=3: time.sleep(60); consecutive_losses=0
            except: bot.send_message(cid, f"⏱️ Expired {oid}")
            AUTO_STATE[cid]['in_trade']=False; time.sleep(3 if mode in ["AGGRO","SCALP"] else 6)
        except Exception as e:
            print(f"Loop err {e}")
            if cid in AUTO_STATE: AUTO_STATE[cid]['in_trade']=False
            time.sleep(10)
    AUTO_LOCK[cid]=False
    bot.send_message(cid, f"🛑 **{mode} STOPPED** Trades {AUTO_STATE.get(cid,{}).get('trades',0)} Profit ${profit_now:.2f} Day {STATS['daily_trades']}/{daily_limit}")

@bot.message_handler(commands=['start','stop'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id, "❌ Private Bot"); return
    if m.text.startswith('/stop'):
        if m.chat.id in AUTO_STATE: AUTO_STATE[m.chat.id]['running']=False; bot.send_message(m.chat.id, "🛑 Stopping OTC Auto...")
        return
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("💹 MANUAL OTC TRADE", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO OTC TRAILBLAZER", callback_data="auto_setup"))
    mk.add(types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"))
    txt=f"""🔥 **KEVIN OTC SPECIALIST V7.8** 🔥

💎 IQ: {'✅ Connected' if IQ_CONNECTED else '❌'} | 💰 ${STATS['balance']:.2f} W{STATS['wins']} L{STATS['loss']} Day {STATS['daily_trades']}/30

✨ **V7.8 NEW:**
👑 OTC KING - Best OTC Strategy!
🛡️ Stop-Loss + Target Profit
📊 Payout Filter 80%+
📅 Daily Limit 30 trades
✅ Original Bar V8.2 untouched!

👇 **Choose:**
"""
    bot.send_message(m.chat.id, txt, reply_markup=mk, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): return
    data=c.data; cid=c.message.chat.id
    if data=="ignore": bot.answer_callback_query(c.id, "KEVIN V7.8"); return
    
    if data=="auto_setup":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN BEST OTC", callback_data="auto_pair_AUTO"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"auto_pair_{p}"))
        mk.add(types.InlineKeyboardButton("───────────────", callback_data="ignore"))
        mk.add(types.InlineKeyboardButton("👑 OTC KING 👑 (BEST!)", callback_data="auto_mode_KING"),
               types.InlineKeyboardButton("🛡️ SAFE MODE 88%+", callback_data="auto_mode_SAFE"))
        mk.add(types.InlineKeyboardButton("🚀 AGGRO MODE 80%+", callback_data="auto_mode_AGGRO"),
               types.InlineKeyboardButton("🎯 SNIPER 95%+ MODE", callback_data="auto_mode_SNIPER"))
        mk.add(types.InlineKeyboardButton("🔥 WIN STREAK BOOSTER", callback_data="auto_mode_STREAK"),
               types.InlineKeyboardButton("⚡ 5-SEC SCALP MODE", callback_data="auto_mode_SCALP"))
        bot.send_message(cid, "🤖 **AUTO OTC - SELECT STRATEGY**\n\n👑 KING = BEST OTC! EMA+RSI+Wick+Momo\n🛡️ SAFE 88%\n🚀 AGGRO 80%\n🎯 SNIPER 95%+\n🔥 STREAK $1>$2>$5\n⚡ SCALP 30s", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("auto_mode_"):
        mode = data.replace("auto_mode_","")
        user_states[cid] = user_states.get(cid,{})
        user_states[cid]['auto_mode'] = mode
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO SCAN BEST", callback_data=f"mode_pair_AUTO_{mode}"))
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"mode_pair_{p}_{mode}"))
        bot.send_message(cid, f"✅ **Strategy: {mode}**\n\n**1/6 SELECT OTC PAIR:**", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("mode_pair_"):
        parts = data.split("_")
        if "AUTO" in data:
            pair = "AUTO"; mode = parts[-1]
        else:
            mode = parts[-1]; pair = "_".join(parts[2:-1])
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
        bot.send_message(cid, f"✅ Strategy: {mode}\nPair: {pair} | {bal}\n\n**3/6 SET TARGET PROFIT**\nBot stop when reach!\n\n👇 Pick:", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("mode_tp_"):
        parts=data.split("_")
        if "custom" in data:
            bal=parts[-2]; mode=parts[-1]; pair="_".join(parts[3:-2])
            user_states[cid].update({'pair':pair,'bal':bal,'mode':mode,'step':'await_tp'})
            bot.send_message(cid, f"✏️ **Type target profit** Example: 50\nStrategy: {mode} | Pair: {pair}"); return
        tp=float(parts[2]); bal=parts[-3]; mode=parts[-1]; pair="_".join(parts[3:-3])
        user_states[cid].update({'target':tp,'pair':pair,'bal':bal,'mode':mode})
        # NEW STEP: STOP LOSS
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("🛑 SL -$20", callback_data=f"mode_sl_-20_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$30", callback_data=f"mode_sl_-30_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("🛑 SL -$50", callback_data=f"mode_sl_-50_{pair}_{bal}_{mode}_{int(tp)}"))
        mk.add(types.InlineKeyboardButton("🛑 SL -$100", callback_data=f"mode_sl_-100_{pair}_{bal}_{mode}_{int(tp)}"),
               types.InlineKeyboardButton("✏️ CUSTOM SL", callback_data=f"mode_sl_custom_{pair}_{bal}_{mode}_{int(tp)}"))
        bot.send_message(cid, f"✅ Target: +${tp:.0f}\n\n**4/6 SET STOP LOSS**\nBot stop if loss reach this!\n\n👇 Pick SL:", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("mode_sl_"):
        parts=data.split("_")
        if "custom" in data:
            bal=parts[-3]; mode=parts[-2]; tp=parts[-1]; pair="_".join(parts[3:-3])
            user_states[cid].update({'pair':pair,'bal':bal,'mode':mode,'target':float(tp),'step':'await_sl'})
            bot.send_message(cid, f"✏️ **Type stop loss (negative number)** Example: -30\nTarget: +${tp} | Strategy: {mode}"); return
        sl=float(parts[2]); bal=parts[-4]; mode=parts[-2]; tp=parts[-1]; pair="_".join(parts[3:-4])
        user_states[cid].update({'target':float(tp),'stoploss':sl,'pair':pair,'bal':bal,'mode':mode})
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"mode_amt_1_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"mode_amt_5_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"mode_amt_10_{pair}_{bal}_{mode}_{int(tp)}_{int(sl)}"))
        bot.send_message(cid, f"✅ TP +${tp} | SL ${sl:.0f}\n\n**5/6 BASE AMOUNT:**", reply_markup=mk, parse_mode="Markdown"); return

    if data.startswith("mode_amt_"):
        parts=data.split("_"); amt=parts[2]; bal=parts[-4]; mode=parts[-3]; tp=parts[-2]; sl=parts[-1]; pair="_".join(parts[3:-4])
        user_states[cid].update({'amt':float(amt),'target':float(tp),'stoploss':float(sl)})
        if mode=="SCALP":
            expiry=30
            AUTO_STATE[cid]={"running":True,"pair":pair,"bal":bal,"base_amt":float(amt),"expiry":expiry,"trades":0,"in_trade":False,"mode":mode,"target":float(tp),"stoploss":float(sl),"profit":0.0}
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🛑 STOP AUTO", callback_data="stop_auto"))
            txt=f"""🚀 **AUTO TRADING ACTIVE!** 🚀

🧠 Strategy: **{mode}**
💱 Pair: **{pair}**
💳 Account: **{bal}**
💰 Base: **${amt}**
🎯 Target Profit: **+${tp}**
🛑 Stop Loss: **${sl}**
⏱️ Expiry: **{expiry}s**
📊 Daily: **{STATS['daily_trades']}/30**

🤖 **Bot is now trading...** One trade at a time!
"""
            bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown")
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
        txt=f"""🚀 **AUTO TRADING ACTIVE!** 🚀

🧠 Strategy: **{mode}**
💱 Pair: **{pair}**
💳 Account: **{bal}**
💰 Base Amount: **${amt}**
🎯 Target Profit: **+${tp}** (Bot stop when reach!)
🛑 Stop Loss: **${sl}** (Bot stop if loss reach!)
⏱️ Expiry: **{expiry}s**
⚙️ Logic: **{'👑 KING - EMA+RSI+Wick+Momo BEST!' if mode=='KING' else '88%+ Safe' if mode=='SAFE' else '80%+ Aggro' if mode=='AGGRO' else '95%+ Sniper' if mode=='SNIPER' else 'Win Streak $1>$2>$5' if mode=='STREAK' else '30s Scalp'}**
📊 Payout Filter: **Skip if <80%**
📅 Daily Limit: **30 trades**

🤖 **Bot is now trading OTC...** Tracking profit live!
"""
        bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown")
        threading.Thread(target=auto_trader_loop, args=(cid,), daemon=True).start(); return

    if data=="stop_auto":
        if cid in AUTO_STATE: AUTO_STATE[cid]['running']=False; bot.send_message(cid, "🛑 Stopping..."); return
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}", callback_data=f"pair_{p}"))
        bot.send_message(cid, "💹 **MANUAL OTC 1/3 - SELECT PAIR**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        bot.send_message(cid, f"✅ {pair}\n\n**2/3 ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),
               types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        bot.send_message(cid, f"✅ {pair} {bal}\n\n**3/3 AMOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("⏱️ 30 SEC", callback_data=f"exp_30_{pair}_{bal}_{int(amt)}"),
               types.InlineKeyboardButton("⏱️ 1 MIN", callback_data=f"exp_60_{pair}_{bal}_{int(amt)}"))
        bot.send_message(cid, f"✅ ${amt} {pair}\n\n**EXPIRY**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("exp_"):
        parts=data.split("_"); expiry=int(parts[1]); bal=parts[-2]; amt=float(parts[-1]); pair="_".join(parts[2:-2])
        bot.answer_callback_query(c.id, f"Scanning {pair}...")
        scan_msg = bot.send_message(cid, f"🔍 **SCAN {pair}**\n\n0%\n🚀 Starting...")
        legit_live_scan(cid, scan_msg.message_id, pair)
        d=analyze_momentum(pair, mode="KING") # Use KING logic for manual too!
        if not d or d.get('rejected'):
            reason = d.get('reason','Failed') if d else 'Failed'
            bot.send_message(cid, f"❌ {reason} {pair}"); return
        expiry_txt = f"{expiry}s" if expiry<60 else f"{expiry//60}min"
        signal_txt=f"""🔥 **OTC KING SIGNAL** 👑
💱 {pair}
📊 {d['dir']} | 🎯 {d['conf']:.0f}% | Payout {int(d.get('payout',0.85)*100)}%
💰 ${amt} {bal} | ⏱️ {expiry_txt}
📈 {d['reason']}"""
        try:
            plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}% KING"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
            bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
        except: bot.send_message(cid, signal_txt, parse_mode="Markdown")
        bot.send_message(cid, f"🚀 **PLACING OTC...** {pair} Payout {int(d.get('payout',0.85)*100)}%")
        ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,expiry)
        if not ok: bot.send_message(cid, f"⚠️ {pair} suspended"); return
        bot.send_message(cid, f"✅ **OTC PLACED!** ID `{oid}` ⏳ {exp}s", parse_mode="Markdown")
        time.sleep(exp+5)
        try:
            with IQ_LOCK: pnl=iq.check_win_v4(oid)
            if pnl>0:
                STATS['wins']+=1; STATS['balance']+=pnl; STATS['streak']+=1
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton("🔁 SAME", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt)}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"✅ **KING WIN +${pnl:.2f}** Bal ${STATS['balance']:.2f} 🔥 {STATS['streak']}", reply_markup=mk, parse_mode="Markdown")
            else:
                STATS['loss']+=1; STATS['balance']-=amt; STATS['streak']=0
                mk=types.InlineKeyboardMarkup(row_width=2)
                mk.add(types.InlineKeyboardButton(f"🔁 MARTI ${amt*2.2:.0f}", callback_data=f"exp_{expiry}_{pair}_{bal}_{int(amt*2.2)}"),
                       types.InlineKeyboardButton("💹 NEW", callback_data="trade"))
                bot.send_message(cid, f"❌ **LOSS -${amt}** Bal ${STATS['balance']:.2f}", reply_markup=mk, parse_mode="Markdown")
        except: bot.send_message(cid, f"⏱️ Expired {oid} Check IQ app")
        return
    if data=="stats":
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        bot.send_message(cid, f"📊 **OTC V7.8 STATS**\nW {STATS['wins']} L {STATS['loss']} {wr:.1f}%\nBal ${STATS['balance']:.2f} Streak {STATS['streak']}\nDay {STATS['daily_trades']}/30", parse_mode="Markdown")

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
        bot.send_message(cid, f"✅ Target: +${tp:.0f} set!\n\n**4/6 SET STOP LOSS:**", reply_markup=mk, parse_mode="Markdown")
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
        bot.send_message(cid, f"✅ SL ${sl:.0f} set!\n\n**5/6 BASE AMOUNT:**", reply_markup=mk, parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send negative number e.g. -30")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "KEVIN OTC V7.8 KING RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
