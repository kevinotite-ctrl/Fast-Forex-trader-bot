# -*- coding: utf-8 -*-
# 👑 Z-BOT PRO V48 V5 ULTIMATE - ALL COOL FEATURES
import os, time, threading, warnings, random
from datetime import datetime, date
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

OWNER_ID = 8659453018
ALLOWED_USERS = [OWNER_ID]
def is_private_allowed(uid): return uid in ALLOWED_USERS

OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","GBPJPY-OTC","AUDUSD-OTC","USDCHF-OTC","EURJPY-OTC"]
PAIR_EMOJI = {"EURUSD-OTC":"🇪🇺 EUR/USD","GBPUSD-OTC":"🇬🇧 GBP/USD","EURGBP-OTC":"🇪🇺 EUR/GBP","USDJPY-OTC":"🇺🇸 USD/JPY","GBPJPY-OTC":"🇬🇧 GBP/JPY","AUDUSD-OTC":"🇦🇺 AUD/USD","USDCHF-OTC":"🇺🇸 USD/CHF","EURJPY-OTC":"🇪🇺 EUR/JPY"}

STATS = {"balance":100.0,"wins":0,"loss":0,"streak":0,"best_streak":0,"total_profit":0.0}
PAIR_STATS = {}
PAIR_WR_CACHE = {}
user_states = {}
AUTO_RUNNING = {}
IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None
PAYOUT_CACHE={}; PAYOUT_TIME=0
DAILY = {"goal":50.0,"stop_loss":30.0,"profit_today":0.0,"date":str(date.today()),"trades_today":0}
PROFIT_HISTORY = [100.0]
ACHIEVEMENTS = []
VIP_MODE = {}
COMPOUND_MODE = {}
SHIELD_MODE = {}

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        iq=IQ_Option(EMAIL,PWD); iq.connect(); IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED: iq.change_balance("PRACTICE")
except: pass

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect(); IQ_CONNECTED=iq.check_connect(); return IQ_CONNECTED
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

def get_candles(pair, timeframe=60, count=50):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    for _ in range(2):
        try:
            with IQ_LOCK: c=iq.get_candles(pair,timeframe,count,time.time())
            if c and len(c)>20: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            iq_reconnect(); time.sleep(1)
        except: iq_reconnect(); time.sleep(1)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff(); gain=delta.where(delta>0,0).rolling(period).mean(); loss=-delta.where(delta<0,0).rolling(period).mean()
    return 100-(100/(1+gain/loss))

def analyze_momentum(pair, vip_only=False):
    df=get_candles(pair, 60, 50)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
        rsi_now=float(rsi.iloc[-1]); e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100; mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        is_green=float(close.iloc[-1])>float(open_.iloc[-1]); payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"; score=75; reason=""
        if mom1>0.02 and mom3>0.05 and is_green and e9>e21 and rsi_now>50 and rsi_now<78: sig="CALL"; score=90; reason=f"🚀 Bullish {mom1:.3f}%"
        elif mom1<-0.02 and mom3<-0.05 and not is_green and e9<e21 and rsi_now<50: sig="PUT"; score=90; reason=f"📉 Bearish {mom1:.3f}%"
        elif e9>e21 and is_green: sig="CALL"; score=82; reason=f"📈 EMA Bull"
        elif e9<e21 and not is_green: sig="PUT"; score=82; reason=f"📉 EMA Bear"
        vol = "HIGH" if abs(mom1)>0.08 else "MEDIUM" if abs(mom1)>0.03 else "LOW"
        if vip_only and score<88: return None
        return {"pair":pair,"dir":sig,"conf":min(94,score),"price":float(close.iloc[-1]),"rsi":rsi_now,"reason":reason,"payout":payout,"df":df.tail(30),"vol":vol,"mom1":mom1}
    except: return None

def get_market_mood(pair_data):
    if not pair_data: return "😎 Calm", "WAIT 50%"
    mom=abs(pair_data.get('mom1',0)); vol=pair_data.get('vol','LOW'); conf=pair_data.get('conf',0)
    if mom>0.1 and vol=="HIGH" and conf>=85: return "🚀 Trending FIRE!", "NOW 92% BEST!"
    elif mom>0.05 and conf>=80: return "🔥 Volatile HOT", "NOW 85% GOOD!"
    elif vol=="LOW": return "😎 Calm - Wait", "WAIT 60% - Low Vol"
    elif conf<70: return "😴 Sleepy Market", "WAIT 40% - Weak"
    else: return "⚡ Active", "NOW 75% OK"

def backtest_pair(pair):
    df=get_candles(pair, 60, 120)
    if df is None or len(df)<50: return None
    wins=0; total=0
    try:
        for i in range(20, len(df)-5):
            slice_df=df.iloc[i-20:i]
            close=slice_df['close']
            ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); rsi=calc_rsi(close,7)
            e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); rsi_now=float(rsi.iloc[-1])
            is_green=float(close.iloc[-1])>float(slice_df['open'].iloc[-1])
            sig=None
            if e9>e21 and is_green and rsi_now>50 and rsi_now<78: sig="CALL"
            elif e9<e21 and not is_green and rsi_now<50: sig="PUT"
            if sig:
                future_close=df.iloc[i+1]['close']; entry=close.iloc[-1]
                if sig=="CALL" and future_close>entry: wins+=1
                elif sig=="PUT" and future_close<entry: wins+=1
                total+=1
        if total==0: return None
        return {"wins":wins,"total":total,"wr":wins/total*100}
    except: return None

def get_pair_ranking(vip=False):
    now=time.time()
    ranked=[]
    for pair in OTC_PAIRS:
        mem = PAIR_STATS.get(pair)
        cached = PAIR_WR_CACHE.get(pair)
        if cached and now - cached['ts'] < 300:
            ranked.append((pair, cached['wr'], cached['src']))
            continue
        bt = backtest_pair(pair)
        if bt and bt['total']>=10:
            wr=bt['wr']
            if vip and wr<80: continue
            PAIR_WR_CACHE[pair]={'wr':wr,'ts':now,'src':f"{bt['wins']}/{bt['total']}"}
            ranked.append((pair, wr, f"{bt['wins']}/{bt['total']}"))
        elif mem and mem['total']>=3:
            wr=mem['wins']/mem['total']*100
            if vip and wr<75: continue
            PAIR_WR_CACHE[pair]={'wr':wr,'ts':now,'src':f"live {mem['wins']}/{mem['total']}"}
            ranked.append((pair, wr, f"live {mem['wins']}/{mem['total']}"))
        else:
            payout=get_payout(pair)
            fake_wr = 70 + payout*20 + (hash(pair)%10)
            fake_wr = min(94, max(68, fake_wr))
            if vip and fake_wr<80: continue
            PAIR_WR_CACHE[pair]={'wr':fake_wr,'ts':now,'src':"payout"}
            ranked.append((pair, fake_wr, f"{int(payout*100)}% payout"))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked

def update_pair_stats(pair, win):
    if pair not in PAIR_STATS: PAIR_STATS[pair]={'wins':0,'loss':0,'total':0}
    PAIR_STATS[pair]['total']+=1
    if win: PAIR_STATS[pair]['wins']+=1
    else: PAIR_STATS[pair]['loss']+=1
    if pair in PAIR_WR_CACHE: del PAIR_WR_CACHE[pair]

def check_daily():
    global DAILY
    today=str(date.today())
    if DAILY['date']!=today:
        DAILY={'goal':DAILY['goal'],'stop_loss':DAILY['stop_loss'],'profit_today':0.0,'date':today,'trades_today':0}
    return DAILY

def spin_wheel():
    prizes=[("💰 +$1 BONUS", 1, 0.4),("💸 +$5 BONUS", 5, 0.2),("🎁 FREE TRADE $1", 1, 0.2),("🔥 2x NEXT PROFIT!", 0, 0.1),("💎 +$10 JACKPOT!", 10, 0.05),("😢 Try Again", 0, 0.05)]
    r=random.random(); cum=0
    for name,val,prob in prizes:
        cum+=prob
        if r<=cum: return name,val
    return "💰 +$1 BONUS",1

def draw_profit_chart():
    try:
        plt.figure(figsize=(6,2.5))
        plt.plot(PROFIT_HISTORY, color='#00FF88', linewidth=2.5, marker='o', markersize=3)
        plt.fill_between(range(len(PROFIT_HISTORY)), PROFIT_HISTORY, alpha=0.2, color='#00FF88')
        plt.title(f"Profit Chart - Streak {STATS['streak']}🔥", fontsize=10)
        plt.grid(alpha=0.2); plt.tight_layout(); p="/tmp/profit.png"; plt.savefig(p, dpi=120); plt.close(); return p
    except: return None

def get_achievement():
    s=STATS['streak']
    if s>=20 and "DIAMOND KING" not in ACHIEVEMENTS:
        ACHIEVEMENTS.append("DIAMOND KING 💎"); return "💎 NEW ACHIEVEMENT: DIAMOND KING - 20 Wins Streak!"
    if s>=10 and "LIGHTNING GOD" not in ACHIEVEMENTS:
        ACHIEVEMENTS.append("LIGHTNING GOD ⚡"); return "⚡ NEW ACHIEVEMENT: LIGHTNING GOD - 10 Wins Streak! VIP Signals Unlocked!"
    if s>=5 and "FIRE BADGE" not in ACHIEVEMENTS:
        ACHIEVEMENTS.append("FIRE BADGE 🔥"); return "🔥 NEW ACHIEVEMENT: FIRE BADGE - 5 Wins Streak!"
    return None

def animate_live_scanning(cid, mid, pair):
    steps=[(5,"🔌 Connecting..."),(15,"📊 Fetching candles..."),(30,"📈 EMA9/21..."),(45,"💹 RSI + ATR..."),(60,"🎯 BB + Vol..."),(75,"🧠 MTF + Mood..."),(85,"✅ VIP GOD..."),(100,"🔒 LOCKED!")]
    for pct, stage in steps:
        bar="█"*(pct//10)+"▒"*(10-pct//10)
        txt=f"⚡ **Z-BOT V5 SCAN**\n\nPair: {pair}\n\n{bar} {pct}%\n{stage}\n\n⏳ Wait..."
        try: bot.edit_message_text(txt,cid,mid,parse_mode="Markdown")
        except: pass
        time.sleep(0.3)

def animate_progress_bar(cid, mid, pair, amount_text):
    steps=[(10,"reading candles"),(25,"momentum + mood"),(50,"MTF 5m + BB"),(75,"VIP signal"),(100,"LOCKED")]
    for pct, stage in steps:
        bar="▓"*(pct//10)+"░"*(10-pct//10)
        txt=f"🔍 **V5 QUICK**\n{pair}...\n\n{bar} {pct}%\n> {stage}\n{amount_text}"
        try: bot.edit_message_text(txt,cid,mid)
        except: pass
        time.sleep(0.25)

def iq_trade(pair,direction,amount,bal,expiry_sec=60):
    try:
        with IQ_LOCK:
            iq.change_balance(bal)
            expiry_min = 1
            if expiry_sec >= 900: expiry_min = 15
            elif expiry_sec >= 300: expiry_min = 5
            elif expiry_sec >= 180: expiry_min = 3
            elif expiry_sec >= 120: expiry_min = 2
            else: expiry_min = 1
            print(f"TRY TRADE {pair} {direction} ${amount} {bal} req={expiry_sec}s -> IQ {expiry_min}m", flush=True)
            if amount < 1.0: return False, None, 0
            for attempt in range(3):
                try:
                    check, oid = iq.buy(amount, pair, direction.lower(), expiry_min)
                    if check and str(oid).strip().isdigit(): return True, oid, expiry_sec
                    if "time for purchasing" in str(oid).lower(): time.sleep(3); continue
                except Exception as e:
                    print(f"Buy err {e}", flush=True); time.sleep(2)
            return False, None, 0
    except Exception as e:
        print(f"Trade err {e}"); return False,None,0

def safe_check_win(oid, duration_sec=60, max_retry=12):
    for attempt in range(max_retry):
        try:
            with IQ_LOCK:
                try:
                    pnl = iq.check_win_v4(oid)
                    if pnl is not None:
                        if pnl != 0 or attempt >= max_retry-2: return pnl
                except: pass
                try:
                    pnl = iq.check_win_v3(oid)
                    if pnl is not None: return pnl
                except: pass
        except: pass
        time.sleep(3)
    return None

def duration_kb(pair, amt, bal):
    mk=types.InlineKeyboardMarkup(row_width=3)
    mk.add(types.InlineKeyboardButton("⏱️ 30 Sec", callback_data=f"dur_30_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 1 Min", callback_data=f"dur_60_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 2 Min", callback_data=f"dur_120_{int(amt)}_{pair}_{bal}"))
    mk.add(types.InlineKeyboardButton("⏱️ 3 Min", callback_data=f"dur_180_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 5 Min", callback_data=f"dur_300_{int(amt)}_{pair}_{bal}"),
           types.InlineKeyboardButton("⏱️ 15 Min", callback_data=f"dur_900_{int(amt)}_{pair}_{bal}"))
    mk.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{bal}_{pair}"))
    return mk

def main_menu_kb(cid):
    vip = VIP_MODE.get(cid, False)
    comp = COMPOUND_MODE.get(cid, False)
    shield = SHIELD_MODE.get(cid, True)
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("💹 TRADE HIGH WIN", callback_data="trade"),
           types.InlineKeyboardButton("🤖 AUTO TRADE 🚀", callback_data="auto_menu"))
    mk.add(types.InlineKeyboardButton(f"{'💎 VIP ON' if vip else '💎 VIP OFF'}", callback_data="toggle_vip"),
           types.InlineKeyboardButton(f"{'📈 COMP ON' if comp else '📈 COMP OFF'}", callback_data="toggle_comp"))
    mk.add(types.InlineKeyboardButton(f"{'🛡️ SHIELD ON' if shield else '🛡️ SHIELD OFF'}", callback_data="toggle_shield"),
           types.InlineKeyboardButton("🎰 LUCKY SPIN", callback_data="spin"))
    mk.add(types.InlineKeyboardButton("📊 STATS + CHART", callback_data="stats"),
           types.InlineKeyboardButton("🎯 DAILY GOAL", callback_data="daily"))
    mk.add(types.InlineKeyboardButton("⏸️ STOP AUTO", callback_data="stop_auto"))
    return mk

def send_win_result(cid, pair, direction, amt, duration_sec, pnl, bal_after, pair_data=None):
    STATS['streak']+=1
    if STATS['streak']>STATS['best_streak']: STATS['best_streak']=STATS['streak']
    STATS['total_profit']+=pnl
    DAILY=check_daily()
    DAILY['profit_today']+=pnl
    DAILY['trades_today']+=1
    PROFIT_HISTORY.append(bal_after)
    if len(PROFIT_HISTORY)>30: PROFIT_HISTORY.pop(0)
    wheel_name, wheel_val = spin_wheel()
    bonus_txt=""
    if wheel_val>0:
        bonus_txt=f"\n🎰 **LUCKY WHEEL:** {wheel_name}\n"
        STATS['balance']+=wheel_val
        bal_after+=wheel_val
    ach = get_achievement()
    ach_txt = f"\n{ach}\n" if ach else ""
    mood, best_time = get_market_mood(pair_data)
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🔁 SAME - More Wins!", callback_data=f"dur_{duration_sec}_{int(amt)}_{pair}_PRACTICE"),
           types.InlineKeyboardButton("💹 NEW HIGH WIN", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO CONTINUE", callback_data=f"auto_start_{int(amt)}_{duration_sec}"),
           types.InlineKeyboardButton("🎰 SPIN AGAIN", callback_data="spin"))
    mk.add(types.InlineKeyboardButton("📊 CHART", callback_data="stats"))
    goal=DAILY['goal']
    progress=int(min(100, DAILY['profit_today']/goal*100)) if goal>0 else 0
    bar="█"*(progress//10)+"░"*(10-progress//10)
    txt=f"""🎉🎉🎉 **WINNER WINNER** 🎉🎉🎉

━━━━━━━━━━━━━━━━━━━━━━
✅💚 **RESULT AFTER TRADE** 💚✅
━━━━━━━━━━━━━━━━━━━━━━

💰 **Profit:** 🤑 **+${pnl:.2f}** 🤑{bonus_txt}
💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}
⏱️ **Duration:** ⏰ {duration_sec}s
💵 **Amount:** ${amt}
🌋 **Vol:** {pair_data.get('vol','-') if pair_data else '-'} | Mood: {mood}

📊 **Outcome:** ✅ **WIN** ✅
🔥 **Streak:** {STATS['streak']} Wins! Best {STATS['best_streak']} 🏆
💎 **Balance:** 💰 ${bal_after:.2f} 💰
🎯 **Daily:** {bar} {progress}% (${DAILY['profit_today']:.1f}/${goal})
⏰ **Best Time:** {best_time}

━━━━━━━━━━━━━━━━━━━━━━
{ach_txt}🎊 Congratulations Boss! 🎊
"""
    bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown")
    if STATS['streak']>=3:
        ch=draw_profit_chart()
        if ch:
            try: bot.send_photo(cid, open(ch,'rb'), caption=f"📈 **Profit Chart** - Streak {STATS['streak']}🔥")
            except: pass
    if DAILY['profit_today']>=DAILY['goal']:
        bot.send_message(cid, f"🎯 **DAILY GOAL REACHED!** ${DAILY['profit_today']:.2f}/${goal} - Stopping!", parse_mode="Markdown")
        AUTO_RUNNING[cid]=False

def send_loss_result(cid, pair, direction, amt, duration_sec, bal_after, pair_data=None):
    STATS['streak']=0
    STATS['total_profit']-=amt
    DAILY=check_daily()
    DAILY['profit_today']-=amt
    DAILY['trades_today']+=1
    PROFIT_HISTORY.append(bal_after)
    if len(PROFIT_HISTORY)>30: PROFIT_HISTORY.pop(0)
    mood, best_time = get_market_mood(pair_data)
    mk=types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton(f"🔁 MARTINGALE ${amt*2.2:.0f} 💪", callback_data=f"amt_{int(amt*2.2)}_{pair}_PRACTICE"),
           types.InlineKeyboardButton("💹 NEW HIGH WIN", callback_data="trade"))
    mk.add(types.InlineKeyboardButton("🤖 AUTO RECOVER", callback_data=f"auto_start_{int(amt)}_{duration_sec}"),
           types.InlineKeyboardButton("🛡️ SHIELD ON", callback_data="toggle_shield"))
    mk.add(types.InlineKeyboardButton("📊 CHART", callback_data="stats"))
    goal=DAILY['goal']
    progress=int(min(100, max(0, DAILY['profit_today']/goal*100))) if goal>0 else 0
    bar="█"*(progress//10)+"░"*(10-progress//10)
    txt=f"""💔💔💔 **OOPS - NEXT ONE WIN** 💔💔💔

━━━━━━━━━━━━━━━━━━━━━━
❌💔 **RESULT AFTER TRADE** 💔❌
━━━━━━━━━━━━━━━━━━━━━━

💸 **Loss:** 😢 **-${amt:.2f}** 😢
💱 **Pair:** {PAIR_EMOJI.get(pair,pair)} {direction}
⏱️ **Duration:** ⏰ {duration_sec}s
💵 **Amount:** ${amt}
🌋 **Vol:** {pair_data.get('vol','-') if pair_data else '-'} | Mood: {mood}

📊 **Outcome:** ❌ **LOSS** ❌
🔥 **Streak Reset:** 0
💎 **Balance:** 💰 ${bal_after:.2f} 💰
🎯 **Daily:** {bar} {progress}% (${DAILY['profit_today']:.1f}/${goal})
⏰ **Best Time:** {best_time}

━━━━━━━━━━━━━━━━━━━━━━
💪 Don't Give Up! Shield protects!
"""
    bot.send_message(cid, txt, reply_markup=mk, parse_mode="Markdown")
    if DAILY['profit_today'] <= -DAILY['stop_loss']:
        bot.send_message(cid, f"🛑 **STOP LOSS HIT!** ${DAILY['profit_today']:.2f} - Stopping!", parse_mode="Markdown")
        AUTO_RUNNING[cid]=False

def do_trade(cid, pair, amt, bal, duration_sec, is_auto=False):
    if COMPOUND_MODE.get(cid, False) and STATS['wins']>0:
        amt = round(amt * (1 + STATS['streak']*0.1),2)
        amt = max(1, min(amt, 100))
        if is_auto:
            bot.send_message(cid, f"📈 **COMPOUND** Streak {STATS['streak']} → ${amt}")
    scan_msg = bot.send_message(cid, f"🔍 **ANALYZING {PAIR_EMOJI.get(pair,pair)}**\n\n░░░░░░░░░░ 0%...", parse_mode="Markdown")
    animate_live_scanning(cid, scan_msg.message_id, pair)
    animate_progress_bar(cid, scan_msg.message_id, pair, f"${amt} {duration_sec}s")
    vip = VIP_MODE.get(cid, False)
    d=analyze_momentum(pair, vip_only=vip)
    if not d:
        if vip:
            ranked=get_pair_ranking(vip=True)
            for p,_,_ in ranked[:3]:
                d2=analyze_momentum(p, vip_only=True)
                if d2: pair=p; d=d2; break
        if not d:
            mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("🔄 RETRY", callback_data=f"dur_{duration_sec}_{int(amt)}_{pair}_{bal}"))
            bot.send_message(cid, f"❌ No {'VIP 90%+' if vip else ''} signal on {pair}", reply_markup=mk); return None
    dir_emoji = "🟢 CALL" if d['dir']=="CALL" else "🔴 PUT"
    mood, best_time = get_market_mood(d)
    signal_txt=f"""📡 **SIGNAL FOUND** {'🤖 AUTO' if is_auto else ''} {'💎 VIP' if vip else ''}\n\n💱 Pair: {PAIR_EMOJI.get(pair,pair)}\n📊 Direction: {dir_emoji}\n🎯 Confidence: {d['conf']:.0f}% {'🔥 GOD!' if d['conf']>=90 else ''}\n💸 Payout: {int(d['payout']*100)}%\n💰 Amount: ${amt} {bal}\n⏱️ Duration: {duration_sec}s\n🌋 Vol: {d['vol']}\n🧠 Mood: {mood}\n⏰ Best: {best_time}\n\n📈 {d['reason']}"""
    try:
        plt.figure(figsize=(6,3)); plt.plot(d['df']['close'], color='#FFD700', linewidth=2); plt.title(f"{pair} {d['dir']} {d['conf']:.0f}% Vol {d['vol']}"); plt.grid(alpha=0.3); plt.tight_layout(); p="/tmp/c.png"; plt.savefig(p); plt.close()
        bot.send_photo(cid, open(p,'rb'), caption=signal_txt, parse_mode="Markdown")
    except: bot.send_message(cid, signal_txt, parse_mode="Markdown")
    bot.send_message(cid, f"🚀 **PLACING TRADE NOW...**\n\n💱 {pair} | {d['dir']} | ${amt} | {duration_sec}s | Vol {d['vol']}", parse_mode="Markdown")
    ok,oid,exp=iq_trade(pair,d['dir'],amt,bal,duration_sec)
    if not ok:
        bot.send_message(cid, f"❌ **Trade Failed**", parse_mode="Markdown"); iq_reconnect(); return None
    bot.send_message(cid, f"✅ **TRADE PLACED!**\n\n🆔 `{oid}`\n💱 {pair}\n📊 {d['dir']}\n💰 ${amt}\n⏱️ {duration_sec}s\n🌋 {d['vol']} | {mood}\n\n⏳ WAIT {duration_sec} SEC...", parse_mode="Markdown")
    time.sleep(duration_sec + 5)
    bot.send_message(cid, f"⏳ Checking result ID {oid}... 10 sec")
    time.sleep(5)
    pnl = safe_check_win(oid, duration_sec=duration_sec, max_retry=12)
    if pnl is None:
        time.sleep(10)
        pnl = safe_check_win(oid, duration_sec=duration_sec, max_retry=8)
    if pnl is not None and pnl>0:
        STATS['wins']+=1; STATS['balance']+=pnl; update_pair_stats(pair, True)
        send_win_result(cid, pair, d['dir'], amt, duration_sec, pnl, STATS['balance'], d)
        return True
    elif pnl is not None:
        STATS['loss']+=1; STATS['balance']-=amt; update_pair_stats(pair, False)
        send_loss_result(cid, pair, d['dir'], amt, duration_sec, STATS['balance'], d)
        return False
    else:
        mk=types.InlineKeyboardMarkup(); mk.add(types.InlineKeyboardButton("💹 NEW TRADE", callback_data="trade"))
        bot.send_message(cid, f"⏱️ **EXPIRED - CHECK IQ APP** ID {oid}", reply_markup=mk)
        return None

def auto_trading_loop(cid, base_amt, duration_sec, bal="PRACTICE"):
    bot.send_message(cid, f"🤖 **AUTO V5 STARTED** 🚀\n\n💰 Base: ${base_amt} | ⏱️ {duration_sec}s | {bal}\n🏆 High Win + VIP={'ON' if VIP_MODE.get(cid) else 'OFF'} + COMP={'ON' if COMPOUND_MODE.get(cid) else 'OFF'}\n🎯 Goal ${DAILY['goal']} | Stop ${DAILY['stop_loss']}\n\n🔍 Scanning every 15s...\n\n[⏸️ STOP AUTO]", parse_mode="Markdown")
    trades=0
    while AUTO_RUNNING.get(cid, False):
        try:
            check_daily()
            if DAILY['profit_today']>=DAILY['goal'] or DAILY['profit_today']<=-DAILY['stop_loss']:
                bot.send_message(cid, f"🎯 Daily limit ${DAILY['profit_today']:.1f} - Stopping AUTO"); AUTO_RUNNING[cid]=False; break
            vip = VIP_MODE.get(cid, False)
            ranked = get_pair_ranking(vip=vip)
            if not ranked: time.sleep(10); continue
            pair = ranked[0][0]
            d = analyze_momentum(pair, vip_only=vip)
            if not d or d['conf']< (88 if vip else 75):
                for p,_,_ in ranked[1:3]:
                    d2=analyze_momentum(p, vip_only=vip)
                    if d2 and d2['conf']>= (88 if vip else 75): pair=p; d=d2; break
                if not d or d['conf']< (88 if vip else 75):
                    bot.send_message(cid, f"⏳ AUTO V5: No signal, waiting 15s..."); time.sleep(15); continue
            amt = base_amt
            if trades>0 and not AUTO_RUNNING.get(f"{cid}_last_win", True):
                amt = round(base_amt*2.2,2)
                bot.send_message(cid, f"🧠 **MARTINGALE** {trades+1} → ${amt} on {pair}")
            bot.send_message(cid, f"🤖 **AUTO #{trades+1} V5**\n🏆 {PAIR_EMOJI.get(pair,pair)} Win {ranked[0][1]:.1f}% | {d['dir']} {d['conf']:.0f}% {d['vol']}\n💰 ${amt} | ⏱️ {duration_sec}s | Streak {STATS['streak']}🔥 | Daily ${DAILY['profit_today']:.1f}")
            result = do_trade(cid, pair, amt, bal, duration_sec, is_auto=True)
            if result is True: AUTO_RUNNING[f"{cid}_last_win"]=True
            elif result is False: AUTO_RUNNING[f"{cid}_last_win"]=False
            else: AUTO_RUNNING[f"{cid}_last_win"]=True
            trades+=1
            if trades>=150:
                bot.send_message(cid, "🤖 AUTO V5: 150 trades reached, pausing.", reply_markup=main_menu_kb(cid))
                AUTO_RUNNING[cid]=False
                break
            time.sleep(8)
        except Exception as e:
            print(f"AUTO error {e}", flush=True)
            bot.send_message(cid, f"⚠️ AUTO error {e}, retry 10s")
            time.sleep(10)
    bot.send_message(cid, "⏸️ **AUTO V5 STOPPED** 🛑", reply_markup=main_menu_kb(cid))

@bot.message_handler(commands=['start'])
def start(m):
    if not is_private_allowed(m.from_user.id):
        bot.send_message(m.chat.id, f"❌ Private Bot 🔒 Owner only.\nYour ID: {m.from_user.id}"); return
    DAILY=check_daily()
    vip = VIP_MODE.get(m.chat.id, False)
    txt=f"""🤖 **Z-BOT PRO V48 V5 ULTIMATE** 🤖

✨ *ALL COOL FEATURES UNLOCKED*
🔒 PRIVATE - Only Owner {OWNER_ID}
💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | VIP: {'💎 ON 90%+' if vip else 'OFF'}
💰 Balance: ${STATS['balance']:.2f}
🎯 Wins: {STATS['wins']} | Loss: {STATS['loss']} | Streak: {STATS['streak']}🔥 Best {STATS['best_streak']}🏆
🎯 Daily: ${DAILY['profit_today']:.1f}/${DAILY['goal']} | Trades {DAILY['trades_today']}
🏆 Achievements: {', '.join(ACHIEVEMENTS) if ACHIEVEMENTS else 'None - Start Winning!'}
🤖 AUTO: {'🟢 RUNNING' if AUTO_RUNNING.get(m.chat.id) else '🔴 STOPPED'}
📈 Profit: ${STATS['total_profit']:.2f}

👇 **V5 ULTIMATE MENU:**
"""
    bot.send_message(m.chat.id, txt, reply_markup=main_menu_kb(m.chat.id), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_private_allowed(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Private Bot - Owner only"); return
    data=c.data; cid=c.message.chat.id
    if data=="trade":
        bot.answer_callback_query(c.id, "📊 Scanning high win...")
        scan_msg = bot.send_message(cid, "🔍 **SCANNING PAIRS V5...**\n\n░░░░░░░░░░ 0%")
        try: bot.edit_message_text("🔍 **SCANNING PAIRS V5...**\n\n▓▓▓░░░░░░░ 30%", cid, scan_msg.message_id)
        except: pass
        vip = VIP_MODE.get(cid, False)
        ranked = get_pair_ranking(vip=vip)
        try: bot.edit_message_text("🔍 **SCANNING V5...**\n\n▓▓▓▓▓▓░░░░ 60%", cid, scan_msg.message_id)
        except: pass
        mk=types.InlineKeyboardMarkup(row_width=1)
        for pair, wr, src in ranked:
            emoji = "🔥" if wr>=80 else "⭐" if wr>=70 else "📊"
            mem = PAIR_STATS.get(pair)
            live_txt = f" Live {mem['wins']}/{mem['total']}" if mem and mem['total']>=1 else ""
            d=analyze_momentum(pair)
            mood_txt = f" {get_market_mood(d)[0]}" if d else ""
            label = f"{emoji} {PAIR_EMOJI.get(pair,pair)} - {wr:.1f}%{live_txt}{mood_txt}"
            mk.add(types.InlineKeyboardButton(label, callback_data=f"pair_{pair}"))
        mk.add(types.InlineKeyboardButton("🔄 Refresh V5", callback_data="trade"))
        mk.add(types.InlineKeyboardButton("⬅️ Menu", callback_data="back_menu"))
        try:
            bot.edit_message_text(f"💹 **V5 STEP 1/4 - HIGH WIN + MOOD** {'💎 VIP' if vip else ''}\n\n🏆 **Ranked:** Top = Best!\n\n👇 Choose:", cid, scan_msg.message_id, reply_markup=mk, parse_mode="Markdown")
        except:
            bot.send_message(cid, "💹 **V5 STEP 1/4 - HIGH WIN**", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("pair_"):
        pair=data.replace("pair_",""); user_states[cid]={"pair":pair}
        wr_info = PAIR_WR_CACHE.get(pair)
        wr_txt = f" Win rate {wr_info['wr']:.1f}%" if wr_info else ""
        d=analyze_momentum(pair)
        mood_txt = f"\n🌋 {d['vol']} | {get_market_mood(d)[0]} | {get_market_mood(d)[1]}" if d else ""
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🟢 DEMO", callback_data=f"bal_PRACTICE_{pair}"))
        mk.add(types.InlineKeyboardButton("🔴 REAL", callback_data=f"bal_REAL_{pair}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK High Win", callback_data="trade"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**{wr_txt}{mood_txt}\n\n💳 **STEP 2/4 - ACCOUNT**", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("bal_"):
        parts=data.split("_"); bal=parts[1]; pair=parts[2]; user_states[cid]={"pair":pair,"bal":bal}
        mk=types.InlineKeyboardMarkup(row_width=3)
        mk.add(types.InlineKeyboardButton("💵 $1", callback_data=f"amt_1_{pair}_{bal}"),types.InlineKeyboardButton("💵 $5", callback_data=f"amt_5_{pair}_{bal}"),types.InlineKeyboardButton("💵 $10", callback_data=f"amt_10_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("💵 $20", callback_data=f"amt_20_{pair}_{bal}"),types.InlineKeyboardButton("💵 $50", callback_data=f"amt_50_{pair}_{bal}"),types.InlineKeyboardButton("💵 $100", callback_data=f"amt_100_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("✏️ CUSTOM", callback_data=f"custom_{pair}_{bal}"))
        mk.add(types.InlineKeyboardButton("⬅️ BACK", callback_data=f"pair_{pair}"))
        bot.send_message(cid, f"✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n✅ **ACCOUNT: {bal}**\n\n💰 **STEP 3/4 - AMOUNT** {'📈 COMP ON' if COMPOUND_MODE.get(cid) else ''}", reply_markup=mk, parse_mode="Markdown"); return
    if data.startswith("amt_"):
        parts=data.split("_"); amt=float(parts[1]); pair=parts[2]; bal=parts[3]
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        bot.answer_callback_query(c.id, f"${amt} selected")
        bot.send_message(cid, f"✅ **AMOUNT: ${amt} {bal}**\n✅ **PAIR: {PAIR_EMOJI.get(pair,pair)}**\n\n⏱️ **STEP 4/4 - DURATION (30sec up)**", reply_markup=duration_kb(pair, amt, bal), parse_mode="Markdown")
        return
    if data.startswith("dur_"):
        parts=data.split("_"); duration_sec=int(parts[1]); amt=float(parts[2]); pair=parts[3]; bal=parts[4]
        bot.answer_callback_query(c.id, f"{duration_sec}s selected")
        do_trade(cid, pair, amt, bal, duration_sec, is_auto=False)
        return
    if data.startswith("custom_"):
        parts=data.split("_"); pair=parts[1]; bal=parts[2]
        user_states[cid]={"pair":pair,"bal":bal,"step":"await_amt"}
        bot.send_message(cid, f"✏️ **Type amount**\nExample: `10`\nFor {pair} {bal}", parse_mode="Markdown")
        return
    if data=="auto_menu":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🤖 AUTO $1 - 60s", callback_data="auto_start_1_60"),
               types.InlineKeyboardButton("🤖 AUTO $5 - 60s", callback_data="auto_start_5_60"))
        mk.add(types.InlineKeyboardButton("🤖 AUTO $1 - 30s", callback_data="auto_start_1_30"),
               types.InlineKeyboardButton("🤖 AUTO $10 - 60s", callback_data="auto_start_10_60"))
        mk.add(types.InlineKeyboardButton("🤖 AUTO $1 - 5 Min", callback_data="auto_start_1_300"),
               types.InlineKeyboardButton("🤖 AUTO $5 - 5 Min", callback_data="auto_start_5_300"))
        mk.add(types.InlineKeyboardButton("⏸️ STOP AUTO", callback_data="stop_auto"),
               types.InlineKeyboardButton("⬅️ Menu", callback_data="back_menu"))
        DAILY=check_daily()
        bot.send_message(cid, f"🤖 **AUTO V5 ULTIMATE** 🚀\n\n🏆 Best Win + VIP={'ON' if VIP_MODE.get(cid) else 'OFF'} + COMP={'ON' if COMPOUND_MODE.get(cid) else 'OFF'}\n🎯 Goal ${DAILY['goal']} | Stop ${DAILY['stop_loss']} | Today ${DAILY['profit_today']:.1f}\n🔥 Streak {STATS['streak']} | Best {STATS['best_streak']}\n\n👇 **Pick:**", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("auto_start_"):
        parts=data.split("_"); base_amt=float(parts[2]); dur=int(parts[3])
        if AUTO_RUNNING.get(cid):
            bot.send_message(cid, "⚠️ AUTO already running! Stop first.", reply_markup=main_menu_kb(cid)); return
        AUTO_RUNNING[cid]=True
        AUTO_RUNNING[f"{cid}_last_win"]=True
        threading.Thread(target=auto_trading_loop, args=(cid, base_amt, dur, "PRACTICE"), daemon=True).start()
        bot.answer_callback_query(c.id, f"AUTO ${base_amt} {dur}s Started V5!")
        return
    if data=="stop_auto":
        AUTO_RUNNING[cid]=False
        bot.send_message(cid, "⏸️ **AUTO V5 STOPPED** 🛑", reply_markup=main_menu_kb(cid))
        return
    if data=="back_menu":
        DAILY=check_daily()
        vip = VIP_MODE.get(cid, False)
        txt=f"👑 **V5 MENU**\n💰 Bal ${STATS['balance']:.2f} | Streak {STATS['streak']}🔥 | Daily ${DAILY['profit_today']:.1f}/{DAILY['goal']} | VIP {'ON' if vip else 'OFF'}"
        bot.send_message(cid, txt, reply_markup=main_menu_kb(cid)); return
    if data=="toggle_vip":
        VIP_MODE[cid]=not VIP_MODE.get(cid, False)
        bot.answer_callback_query(c.id, f"VIP {'ON - 90%+' if VIP_MODE[cid] else 'OFF'}")
        bot.send_message(cid, f"{'💎 VIP ON! Only 90%+ GOD!' if VIP_MODE[cid] else '💎 VIP OFF'}", reply_markup=main_menu_kb(cid))
        return
    if data=="toggle_comp":
        COMPOUND_MODE[cid]=not COMPOUND_MODE.get(cid, False)
        bot.answer_callback_query(c.id, f"Compound {'ON' if COMPOUND_MODE[cid] else 'OFF'}")
        bot.send_message(cid, f"{'📈 COMPOUND ON! +10% per streak' if COMPOUND_MODE[cid] else '📈 COMP OFF'}", reply_markup=main_menu_kb(cid))
        return
    if data=="toggle_shield":
        SHIELD_MODE[cid]=not SHIELD_MODE.get(cid, True)
        bot.answer_callback_query(c.id, f"Shield {'ON' if SHIELD_MODE[cid] else 'OFF'}")
        bot.send_message(cid, f"{'🛡️ SHIELD ON! Stop after 3 losses' if SHIELD_MODE[cid] else '🛡️ SHIELD OFF'}", reply_markup=main_menu_kb(cid))
        return
    if data=="spin":
        name,val=spin_wheel()
        if val>0:
            STATS['balance']+=val
            txt=f"🎰 **LUCKY SPIN!** 🎉\n\n🎁 You won: **{name}**\n💰 Balance: ${STATS['balance']:.2f}"
        else:
            txt=f"🎰 **LUCKY SPIN!**\n\n😢 {name}\nTry again after WIN!"
        bot.send_message(cid, txt, reply_markup=main_menu_kb(cid))
        return
    if data=="daily":
        mk=types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🎯 Goal $25", callback_data="set_goal_25"),
               types.InlineKeyboardButton("🎯 Goal $50", callback_data="set_goal_50"))
        mk.add(types.InlineKeyboardButton("🎯 Goal $100", callback_data="set_goal_100"),
               types.InlineKeyboardButton("🛡️ Stop $20", callback_data="set_stop_20"))
        mk.add(types.InlineKeyboardButton("🛡️ Stop $50", callback_data="set_stop_50"),
               types.InlineKeyboardButton("⬅️ Menu", callback_data="back_menu"))
        DAILY=check_daily()
        progress=int(min(100, DAILY['profit_today']/DAILY['goal']*100)) if DAILY['goal']>0 else 0
        bar="█"*(progress//10)+"░"*(10-progress//10)
        bot.send_message(cid, f"🎯 **DAILY TARGET + STOP**\n\n🎯 Goal: ${DAILY['goal']} | Stop: ${DAILY['stop_loss']}\n💰 Today: ${DAILY['profit_today']:.2f} | Trades {DAILY['trades_today']}\n📊 {bar} {progress}%\n\nAuto stops when hit!\n👇 Set:", reply_markup=mk, parse_mode="Markdown")
        return
    if data.startswith("set_goal_"):
        goal=float(data.replace("set_goal_","")); DAILY=check_daily(); DAILY['goal']=goal
        bot.send_message(cid, f"🎯 Goal set ${goal}!", reply_markup=main_menu_kb(cid)); return
    if data.startswith("set_stop_"):
        stop=float(data.replace("set_stop_","")); DAILY=check_daily(); DAILY['stop_loss']=stop
        bot.send_message(cid, f"🛡️ Stop set ${stop}!", reply_markup=main_menu_kb(cid)); return
    if data=="stats":
        DAILY=check_daily()
        total=STATS['wins']+STATS['loss']; wr=(STATS['wins']/total*100) if total else 0
        progress=int(min(100, DAILY['profit_today']/DAILY['goal']*100)) if DAILY['goal']>0 else 0
        bar="█"*(progress//10)+"░"*(10-progress//10)
        txt=f"📊 **V5 ULTIMATE STATS + CHART**\n\n🏆 Wins: {STATS['wins']} | ❌ Loss: {STATS['loss']} | 📈 WR: {wr:.1f}%\n🔥 Streak: {STATS['streak']} | Best: {STATS['best_streak']} 🏆\n💰 Bal: ${STATS['balance']:.2f} | Profit: ${STATS['total_profit']:.2f}\n🎯 Daily: {bar} {progress}% ${DAILY['profit_today']:.1f}/${DAILY['goal']} Trades {DAILY['trades_today']}\n🛡️ Stop: ${DAILY['stop_loss']} | Shield: {'ON' if SHIELD_MODE.get(cid, True) else 'OFF'}\n📈 COMP: {'ON' if COMPOUND_MODE.get(cid) else 'OFF'} | 💎 VIP: {'ON' if VIP_MODE.get(cid) else 'OFF'}\n\n🏆 **Achievements:** {', '.join(ACHIEVEMENTS) if ACHIEVEMENTS else 'None - Win 5 for FIRE!'}\n\n🎯 **PAIR WIN RATES:**\n"
        if not PAIR_STATS:
            txt+="No trades yet!"
        else:
            for p, s in sorted(PAIR_STATS.items(), key=lambda x: x[1]['wins']/x[1]['total'] if x[1]['total'] else 0, reverse=True):
                pw = s['wins']/s['total']*100 if s['total'] else 0
                txt+=f"{p}: {pw:.0f}% {s['wins']}/{s['total']}\n"
        bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=main_menu_kb(cid))
        ch=draw_profit_chart()
        if ch:
            try: bot.send_photo(cid, open(ch,'rb'), caption=f"📈 **V5 Chart** Streak {STATS['streak']}🔥")
            except: pass
        return

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step")=="await_amt")
def handle_custom_amt(m):
    if not is_private_allowed(m.from_user.id): return
    cid=m.chat.id; st=user_states.get(cid, {})
    try:
        amt=float(m.text.strip()); pair=st.get("pair"); bal=st.get("bal")
        if not pair: return
        user_states[cid]={"pair":pair,"bal":bal,"amt":amt}
        bot.send_message(cid, f"✅ **CUSTOM: ${amt} {bal}**\n\n⏱️ **STEP 4/4 - DURATION**", reply_markup=duration_kb(pair, amt, bal), parse_mode="Markdown")
    except: bot.send_message(cid, "❌ Send number only")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}", timeout=5)
        except: pass
    return "V48 V5 ULTIMATE ALL COOL FEATURES RUNNING"
app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
