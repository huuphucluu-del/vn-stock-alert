import os, time, warnings
import pandas as pd
import numpy as np
from datetime import datetime
import requests

warnings.filterwarnings('ignore')

# ============================================================
# CẤU HÌNH — chỉnh tại đây
# ============================================================
TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
NGAY_BAT_DAU     = '2023-01-01'
NGUONG_GAN_MA200 = 3.0   # ±3% quanh MA200
DANH_SACH        = 'VN100' # VN30 hoặc VN100

VN30_LIST = [
    'VCB','BID','CTG','TCB','MBB','VPB','ACB','HPG','GAS','VHM',
    'VIC','MSN','SAB','PLX','MWG','FPT','VNM','POW','HDB','STB',
    'EIB','SSI','VND','HCM','PDR','NVL','VRE','BCM','VJC','SHB'
]
VN100_EXTRA = [
    'DPM','PVD','PVT','REE','GMD','VCS','HAH','DBC','PAN','NSC',
    'BSR','OIL','CII','FCN','CTD','HBC','PC1','TMS','VTO','QNS',
    'SBT','LSS','HAG','HNG','AGR','SJS','TDM','KDH','DXG','NLG',
    'GEX','DCM','HDG','LPB','VIB','OCB','TPB','BAF','MSH','TNG'
]
VN100_LIST = VN30_LIST + VN100_EXTRA
symbols = VN30_LIST if DANH_SACH == 'VN30' else VN100_LIST

# ============================================================
SOURCES = ['VCI','TCBS','KBS','MSN']

def calc_ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def get_close_col(df):
    df.columns = [c.lower() for c in df.columns]
    for name in ['close','dong_cua','gia_dong_cua','c']:
        if name in df.columns:
            return name
    num_cols = df.select_dtypes(include=[np.number]).columns
    return num_cols[3] if len(num_cols) > 3 else num_cols[-1]

def get_history(symbol):
    from vnstock import Vnstock
    today = datetime.today().strftime('%Y-%m-%d')
    for src in SOURCES:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            df = stock.quote.history(start=NGAY_BAT_DAU, end=today, interval='1D')
            if df is not None and len(df) >= 55:
                return df, src
        except:
            continue
    return None, None

def analyze(symbol):
    try:
        df, src = get_history(symbol)
        if df is None:
            return None

        df = df.sort_values(df.columns[0]).reset_index(drop=True)
        close_col = get_close_col(df)
        closes = df[close_col].astype(float).reset_index(drop=True)

        price      = closes.iloc[-1]
        price_prev = closes.iloc[-2]
        change_pct = (price - price_prev) / price_prev * 100

        # MA200
        if len(closes) >= 201:
            ma200_t  = closes.iloc[-200:].mean()
            ma200_p  = closes.iloc[-201:-1].mean()
            cross200 = (price_prev <= ma200_p) and (price > ma200_t)
            near200  = abs(price - ma200_t) / ma200_t * 100 <= NGUONG_GAN_MA200
            diff200  = (price - ma200_t) / ma200_t * 100
        else:
            ma200_t = None; cross200 = False; near200 = False; diff200 = None

        # MA50
        if len(closes) >= 51:
            ma50_t  = closes.iloc[-50:].mean()
            ma50_p  = closes.iloc[-51:-1].mean()
            cross50 = (price_prev <= ma50_p) and (price > ma50_t)
        else:
            ma50_t = None; cross50 = False

        # MACD
        if len(closes) >= 35:
            macd_line   = calc_ema(closes, 12) - calc_ema(closes, 26)
            signal_line = calc_ema(macd_line, 9)
            macd_cross  = (macd_line.iloc[-2] <= signal_line.iloc[-2]) and \
                          (macd_line.iloc[-1]  >  signal_line.iloc[-1])
        else:
            macd_cross = False

        score = cross200*4 + cross50*2 + macd_cross*1

        return {
            'sym': symbol, 'price': price, 'change': change_pct,
            'ma200': ma200_t, 'ma50': ma50_t,
            'cross200': cross200, 'cross50': cross50,
            'macd': macd_cross, 'near200': near200,
            'diff200': diff200, 'score': score
        }
    except Exception as e:
        print(f'  Lỗi {symbol}: {e}')
        return None

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('Chưa có token Telegram'); return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    # Chia nhỏ nếu message > 4096 ký tự
    max_len = 4000
    parts = [msg[i:i+max_len] for i in range(0, len(msg), max_len)]
    for part in parts:
        r = requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID,
                                     'text': part, 'parse_mode': 'HTML'})
        if r.status_code == 200:
            print(f'✅ Telegram OK ({len(part)} ký tự)')
        else:
            print(f'❌ Telegram lỗi: {r.text[:100]}')
        time.sleep(0.5)

# ============================================================
# MAIN
# ============================================================
print(f'🔍 Quét {len(symbols)} mã — {datetime.now().strftime("%H:%M %d/%m/%Y")}')
print('─' * 50)

results = []
for i, sym in enumerate(symbols, 1):
    print(f'  [{i:2d}/{len(symbols)}] {sym}', end=' ')
    r = analyze(sym)
    if r:
        results.append(r)
        if r['score'] > 0:
            sigs = []
            if r['cross200']: sigs.append('🟢MA200↑')
            if r['cross50']:  sigs.append('🔵MA50↑')
            if r['macd']:     sigs.append('🟡MACD×')
            print(f'⚡ {" ".join(sigs)}')
        else:
            print(f'✓ {r["price"]:,.0f} ({r["change"]:+.1f}%)')
    else:
        print('❌ bỏ qua')
    time.sleep(0.4)

print('─' * 50)
print(f'✅ Xong — {len(results)} mã có dữ liệu')

# ============================================================
# BUILD TIN NHẮN TELEGRAM
# ============================================================
now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

signal_list = [r for r in results if r['score'] > 0]
near_list   = [r for r in results if not r['score'] and r.get('near200') and r['ma200']]

msg = f'<b>📊 Tín hiệu MA Chứng khoán VN</b>\n'
msg += f'<i>{now_str} | {len(results)} mã {DANH_SACH}</i>\n'
msg += '─' * 28 + '\n'

# --- Phần 1: Cắt MA ---
if signal_list:
    msg += f'\n<b>⚡ CẮT MA ({len(signal_list)} mã):</b>\n'
    for r in sorted(signal_list, key=lambda x: -x['score']):
        sigs = []
        if r['cross200']: sigs.append('🟢 Cắt MA200↑')
        if r['cross50']:  sigs.append('🔵 Cắt MA50↑')
        if r['macd']:     sigs.append('🟡 MACD×Signal')
        msg += f'\n<b>{r["sym"]}</b>  {r["price"]:,.0f}đ  ({r["change"]:+.2f}%)\n'
        msg += '   ' + ' | '.join(sigs) + '\n'
        if r['ma200']:
            msg += f'   MA200={r["ma200"]:,.0f}  MA50={r["ma50"]:,.0f}\n'
else:
    msg += '\n✅ Không có mã cắt MA hôm nay\n'

# --- Phần 2: Gần MA200 ---
if near_list:
    msg += f'\n<b>⚠️ GẦN MA200 ±{NGUONG_GAN_MA200}% ({len(near_list)} mã):</b>\n'
    near_sorted = sorted(near_list, key=lambda x: abs(x['diff200']))
    for r in near_sorted:
        d = r['diff200']
        vi_tri = f'+{d:.1f}%' if d >= 0 else f'{d:.1f}%'
        flag = 'trên' if d >= 0 else 'dưới'
        msg += f'<b>{r["sym"]}</b>  {r["price"]:,.0f}đ  ({r["change"]:+.2f}%)  — {flag} {vi_tri} MA200\n'
else:
    msg += f'\n⚪ Không có mã nào trong vùng ±{NGUONG_GAN_MA200}% MA200\n'

msg += f'\n<i>Bot tự động chạy 16:00 mỗi ngày giao dịch</i>'

print('\n' + '='*50)
print('TIN NHẮN TELEGRAM:')
print(msg.replace('<b>','').replace('</b>','').replace('<i>','').replace('</i>',''))
print('='*50)

send_telegram(msg)
