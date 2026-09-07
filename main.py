import os, threading, time, requests, asyncio
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

app = Flask(__name__)
@app.route('/')
def home(): return "NOVA MERIDIAN V3.2 DUAL API - LIVE ON RENDER", 200
@app.route('/health')
def health(): return "OK", 200

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SETTINGS = {"alert_on": True, "range": 30, "bin_step": 50, "strategy": "spot", "mcap_min": 250000, "mcap_max": 800000, "source": "both"}
alerted = set()

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔔 Alert {'ON 🟢' if SETTINGS['alert_on'] else 'OFF 🔴'} | {SETTINGS['source'].upper()}", callback_data='toggle_alert')],
        [InlineKeyboardButton("📈 Open", callback_data='open'), InlineKeyboardButton("📉 Exit", callback_data='exit')],
        [InlineKeyboardButton("⚙️ Setting", callback_data='setting'), InlineKeyboardButton("📅 PnL", callback_data='pnl')],
        [InlineKeyboardButton("📊 Meteora", callback_data='check_meteora'), InlineKeyboardButton("🔍 DexScreener", callback_data='check_dex')],
        [InlineKeyboardButton("⚡ DUAL BOTH", callback_data='check_both')]
    ])

def screening_meteora():
    found=[]
    try:
        r=requests.get("https://dlmm-api.meteora.ag/pair/all", timeout=15)
        data=r.json()
        pairs = data.get('pairs', []) if isinstance(data, dict) else data
        for p in pairs[:80]:
            try:
                vol=float(p.get('volume',{}).get('day',0) or 0)
                tvl=float(p.get('liquidity',0) or 0)
                fees=float(p.get('fees',{}).get('day',0) or 0)
                fee_tvl=(fees/tvl*100) if tvl>0 else 0
                bin_step=int(p.get('binStep',0) or 0)
                name=p.get('name','Unknown')
                addr=p.get('address','')
                if vol>=1_000_000 and 12000<=tvl<=70000 and fees>=30 and fee_tvl>=7 and bin_step in [25,50,80,100]:
                    found.append({"source":"METEORA","name":name,"vol":vol,"tvl":tvl,"fees":fees,"fee_tvl":fee_tvl,"bin":bin_step,"addr":addr})
            except: continue
    except Exception as e:
        print(f"Meteora err {e}")
    return found

def screening_dexscreener():
    found=[]
    try:
        urls=["https://api.dexscreener.com/latest/dex/search/?q=SOL","https://api.dexscreener.com/latest/dex/pairs/solana"]
        for url in urls:
            try:
                r=requests.get(url, timeout=15)
                data=r.json()
                pairs=data.get('pairs',[]) if isinstance(data, dict) else data
                for p in pairs[:80]:
                    try:
                        vol=float(p.get('volume',{}).get('h24',0) or 0)
                        mcap=float(p.get('fdv',0) or p.get('marketCap',0) or 0)
                        liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                        pair_addr=p.get('pairAddress','')
                        base=p.get('baseToken',{}).get('symbol','')
                        quote=p.get('quoteToken',{}).get('symbol','')
                        name=f"{base}/{quote}"
                        if vol>=1_000_000 and 250000<=mcap<=800000 and 12000<=liq<=70000:
                            fee_tvl_proxy = (vol*0.01 / liq *100) if liq>0 else 0
                            found.append({"source":"DEXSCREENER","name":name,"vol":vol,"tvl":liq,"mcap":mcap,"fees":vol*0.01,"fee_tvl":fee_tvl_proxy,"bin":"N/A","addr":pair_addr, "url":p.get('url','')})
                            if len(found)>=5: break
                    except: continue
                if found: break
            except: continue
    except Exception as e:
        print(f"Dex err {e}")
    return found

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🚀 NOVA MERIDIAN V3.2 - RENDER LIVE\nDUAL: METEORA + DEXSCREENER\nVol>1M | Mcap 250K-800K | TVL 12K-70K\nAuto alert ON tiap 3 menit!", reply_markup=kb_main())

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer()
    d=q.data
    if d=='toggle_alert':
        SETTINGS['alert_on']=not SETTINGS['alert_on']
        await q.edit_message_text(f"Alert: {'ON 🟢' if SETTINGS['alert_on'] else 'OFF 🔴'}", reply_markup=kb_main())
    elif d=='setting':
        kb=[[InlineKeyboardButton("Range 30%", callback_data='sr_30'), InlineKeyboardButton("Range 45%", callback_data='sr_45')], [InlineKeyboardButton("Bin 25", callback_data='sb_25'), InlineKeyboardButton("Bin 50", callback_data='sb_50'), InlineKeyboardButton("Bin 80", callback_data='sb_80'), InlineKeyboardButton("Bin 100", callback_data='sb_100')], [InlineKeyboardButton("BOTH", callback_data='src_both'), InlineKeyboardButton("METEORA", callback_data='src_met'), InlineKeyboardButton("DEX", callback_data='src_dex')], [InlineKeyboardButton("⬅️ Back", callback_data='back')]]
        await q.edit_message_text(f"⚙️ SETTING Range:{SETTINGS['range']}% Bin:{SETTINGS['bin_step']} Src:{SETTINGS['source']}", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith('sr_'):
        SETTINGS['range']=int(d.split('_')[-1])
        await q.edit_message_text(f"Range {SETTINGS['range']}%", reply_markup=kb_main())
    elif d.startswith('sb_'):
        SETTINGS['bin_step']=int(d.split('_')[-1])
        await q.edit_message_text(f"Bin {SETTINGS['bin_step']}", reply_markup=kb_main())
    elif d.startswith('src_'):
        SETTINGS['source']=d.split('_')[-1]
        await q.edit_message_text(f"Source {SETTINGS['source']}", reply_markup=kb_main())
    elif d=='check_meteora':
        await q.edit_message_text("⏳ Screening Meteora...")
        res=screening_meteora()
        if res:
            txt="\n\n".join([f"✅ {x['name']}\nVol ${x['vol']/1e6:.2f}M | TVL ${x['tvl']/1000:.1f}K | Fees ${x['fees']:.0f} | Fee/TVL {x['fee_tvl']:.1f}% | Bin {x['bin']}" for x in res[:5]])
            await context.bot.send_message(chat_id=q.message.chat_id, text=f"🚨 METEORA {len(res)}:\n\n{txt}", reply_markup=kb_main())
        else:
            await context.bot.send_message(chat_id=q.message.chat_id, text="Meteora: Belum match kriteria ketat", reply_markup=kb_main())
    elif d=='check_dex':
        await q.edit_message_text("⏳ Screening DexScreener...")
        res=screening_dexscreener()
        if res:
            txt="\n\n".join([f"✅ {x['name']}\nMcap ${x.get('mcap',0)/1000:.0f}K | Vol ${x['vol']/1e6:.2f}M | Liq ${x['tvl']/1000:.1f}K | {x.get('url','')}" for x in res[:5]])
            await context.bot.send_message(chat_id=q.message.chat_id, text=f"🔍 DEX {len(res)}:\n\n{txt}", reply_markup=kb_main())
        else:
            await context.bot.send_message(chat_id=q.message.chat_id, text="Dex: Belum ada Mcap 250K-800K", reply_markup=kb_main())
    elif d=='check_both':
        await q.edit_message_text("⚡ DUAL SCREENING...")
        met=screening_meteora()
        dex=screening_dexscreener()
        total=len(met)+len(dex)
        msg=f"⚡ DUAL: METEORA {len(met)} + DEX {len(dex)} = {total}\n\n"
        if met: msg+="METEORA:\n"+"\n".join([f"• {x['name']} Vol ${x['vol']/1e6:.1f}M TVL ${x['tvl']/1000:.0f}K" for x in met[:3]])+"\n\n"
        if dex: msg+="DEX:\n"+"\n".join([f"• {x['name']} Mcap ${x.get('mcap',0)/1000:.0f}K Vol ${x['vol']/1e6:.1f}M" for x in dex[:3]])
        if total==0: msg+="Belum match. Auto cek tiap 3 menit!"
        await context.bot.send_message(chat_id=q.message.chat_id, text=msg, reply_markup=kb_main())
    elif d=='back':
        await q.edit_message_text("🚀 NOVA V3.2 READY", reply_markup=kb_main())
    elif d=='pnl':
        await q.edit_message_text("📅 PNL +15.7% September", reply_markup=kb_main())
    elif d in ['open','exit']:
        await q.edit_message_text(f"{d} - soon", reply_markup=kb_main())

def auto_loop(bot_app):
    while True:
        time.sleep(180)
        if SETTINGS['alert_on'] and CHAT_ID:
            try:
                all_found=[]
                if SETTINGS['source'] in ['both','meteora','met','src_met','bother','met']: all_found+=screening_meteora()
                if SETTINGS['source'] in ['both','dex','dexscreener','src_dex','bother','both']: all_found+=screening_dexscreener()
                # fix both case
                if not all_found and SETTINGS['source']=='both':
                    all_found=screening_meteora()+screening_dexscreener()
                for item in all_found:
                    addr=item['addr']
                    if addr in alerted: continue
                    msg=f"🚨 AUTO {item['source']} 🚨\n\nToken: {item['name']}\nVol: ${item['vol']/1e6:.2f}M\nTVL: ${item['tvl']/1000:.1f}K\nMcap: ${item.get('mcap',0)/1000:.0f}K\nFees: ${item.get('fees',0):.0f}\nFee/TVL: {item.get('fee_tvl',0):.1f}%\nBin: {item.get('bin','N/A')}\n\n{ item.get('url','')}"
                    asyncio.run(bot_app.bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=kb_main()))
                    alerted.add(addr)
                    break
            except Exception as e:
                print(f"auto err {e}")

def run_bot():
    if not TOKEN: 
        print("No token")
        return
    application=Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CallbackQueryHandler(handle))
    threading.Thread(target=auto_loop, args=(application,), daemon=True).start()
    print("NOVA RENDER STARTED")
    application.run_polling()

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port=int(os.environ.get("PORT",10000))
    app.run(host='0.0.0.0', port=port)
