#!/usr/bin/env python3
"""
Spending dashboard builder
==========================

Put your statements in one folder and run:

    python3 spending_dashboard.py                 # reads the folder this script is in
    python3 spending_dashboard.py /path/to/folder # or any other folder

It reads every statement it finds there:
  * Excel or CSV bank statements (.xls, .xlsx, .csv), e.g. HDFC, SBI, ICICI exports
  * PhonePe statement PDFs (.pdf)

and writes  dashboard.html  next to them, then opens it in your browser.
Add or replace statement files, run it again, and the dashboard shows the new data.
The same payment appearing in two overlapping exports is only counted once.

One-time setup (in Terminal):

    pip3 install pandas xlrd openpyxl pdfplumber

Your own categories: create  my_categories.csv  in the same folder with two columns,
keyword,category  (one rule per line). Any payment whose payee or UPI note contains the
keyword gets that category. These rules are checked before the built-in ones below.
    keyword,category
    SUBASHINI,Home & Household
    PRABHAS KITCHEN,Food & Dining
"""
import csv
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime

# ---------------------------------------------------------------- settings you can edit
# Names on your own accounts: money moved between them is never counted as spending.
OWN_ACCOUNT_NAMES = ['NIVEDHA']
# People whose transfers are kept apart (shown, but only counted when you switch them on).
FAMILY = {'ARUNPRASHANTH': 'Arun', 'ARUN': 'Arun'}
FAMILY_CATEGORY = 'Transfers to Arun'

# Built-in rules, checked in order. Keywords are matched against "payee + UPI note", upper-case.
RULES = [
    ('Rent', [' RENT']),
    ('Loans & EMI', [' EMI', 'LOAN', 'BAJAJ FIN']),
    ('Transport', ['PETROL', 'DIESEL', 'FUEL', 'UBER', 'OLA ', 'RAPIDO', 'METRO', 'IRCTC', 'REDBUS', 'FASTAG', 'PARKING', 'AUTO ', 'CAB ', 'MAKEMYTRIP', 'TRAIN', 'BUS TICKET', 'FLIGHT']),
    ('Subscriptions & Recharges', ['RECHARGE', 'EURONET', 'NETFLIX', 'SPOTIFY', 'PRIME', 'HOTSTAR', 'JIOCINEMA', 'YOUTUBE',
                                   'AIRTEL', 'JIO ', 'BSNL', 'BROADBAND', 'SUBSCRIPTION', 'GOOGLE PLAY', 'APPLE.COM']),
    ('Health & Care', ['APOLLO', 'PHARMA', 'MEDICAL', 'TABLET', 'HOSPITAL', 'CLINIC', 'C RAJA', 'MEDPLUS', 'LAB ', 'GYM', 'CULT']),
    ('Entertainment', ['THIRAIARANGAM', 'CINEMA', 'THEATRE', 'PVR', 'INOX', 'BOOKMYSHOW']),
    ('Food & Dining', ['SWIGGY', 'ZOMATO', 'DOMINOS', 'PIZZA', 'KITCHEN', 'HOTEL', 'SWEETS', 'LASSI', 'LESSI', 'JUICE',
                       'PANI PURI', 'PORI', 'IYYENGAR', 'CAKE GURU', 'PAYASAM', 'MAHENDRAN', 'RESTAURANT', 'CAFE', 'BIRYANI',
                       'BAKERY', 'TEA ', 'COFFEE']),
    ('Groceries', ['SUPER MARKET', 'SUPERMARKET', 'HYPER', 'MART', 'BLINKIT', 'ZEPTO', 'BIGBASKET', 'INSTAMART', 'SAKKARAI',
                   'GROCER', 'VEGETABLE', 'FRUITS', 'MILK']),
    ('Shopping', ['TRENDS', 'GRT ', 'JEWELL', 'AMAZON', 'FLIPKART', 'MYNTRA', 'MEESHO', 'AJIO', 'NYKAA', 'CROMA', 'RELIANCE DIGITAL', 'FIREWORKS', 'CRACKERS', 'DECATHLON']),
    ('Home & Household', ['WASHING MACHINE', 'CCTV', 'SATHYA AGENCIES', 'SRI KRISHNA AGENCIES', 'ELECTRICAL', 'HARDWARE',
                          'FURNITURE', 'ELECTRICITY', 'TNEB', 'GAS ']),
    ('Services', ['DTDC', 'COURIER', 'TAILOR', 'SALON', 'LAUNDRY', 'REPAIR']),
]
OUTPUT_NAME = 'dashboard.html'
# --------------------------------------------------------------------------------------

logging.getLogger('pdfminer').setLevel(logging.ERROR)


def need(module, pip_name=None):
    try:
        return __import__(module)
    except ImportError:
        sys.exit(f'Missing Python package "{pip_name or module}". Run:  pip3 install {pip_name or module}')


# ---------------------------------------------------------------- categorising
def load_user_rules(folder):
    path = os.path.join(folder, 'my_categories.csv')
    rules = []
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8-sig') as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0].strip() and row[0].strip().lower() != 'keyword':
                    rules.append((row[0].strip().upper(), row[1].strip()))
    return rules


def categorize(r, user_rules):
    text = f" {r['payee']} {r['remark']} ".upper()
    raw = f" {r['raw']} ".upper()
    if any(n in text or n in raw for n in OWN_ACCOUNT_NAMES) or 'TRANSFER TO XX' in raw:
        return 'Between own accounts'
    if r['direction'] == 'in':
        return 'Money in'
    for key, cat in user_rules:
        if key in text:
            return cat
    if raw.strip().startswith('NWD') or 'ATM' in raw:
        return 'Cash withdrawals'
    if any(re.search(rf'\b{k}(\d|\b)', text) for k in FAMILY):
        return FAMILY_CATEGORY
    for cat, keys in RULES:
        if any(k in text or k in raw for k in keys):
            return cat
    return 'People & other'


def tidy(name):
    name = re.sub(r'\s+', ' ', str(name)).strip(' -')
    up = name.upper()
    for key in FAMILY:
        if re.match(rf'^{key}(\d|\b)', up):
            return key.title()
    for key, nice in [('APOLLO PHARM', 'Apollo Pharmacy'), ('SWIGGY', 'Swiggy'), ('BLINKIT', 'Blinkit'), ('ZOMATO', 'Zomato')]:
        if key in up:
            return nice
    return name.title() if name.isupper() else name


# ---------------------------------------------------------------- account names
def account_name(path):
    f = os.path.basename(path).lower()
    digits = re.search(r'_(\d{4})_', f) or re.search(r'(\d{4})', f)
    for bank in ['hdfc', 'icici', 'axis', 'kotak', 'canara', 'indian', 'iob', 'yes', 'idfc', 'federal']:
        if bank in f:
            return f'{bank.upper()} ••{digits.group(1)}' if digits else bank.upper()
    if 'sbi' in f:
        return 'SBI (PhonePe)' if f.endswith('.pdf') else 'SBI'
    if 'phonepe' in f:
        return 'PhonePe'
    return os.path.splitext(os.path.basename(path))[0]


# ---------------------------------------------------------------- PhonePe PDF
def pdf_text(path):
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except ImportError:
        pass
    try:
        return subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        sys.exit('To read PDF statements, run:  pip3 install pdfplumber')


def read_phonepe_pdf(path):
    lines = [l.strip() for l in pdf_text(path).splitlines()]
    head = re.compile(r'^(\w{3} \d{1,2}, \d{4})\s+(.+?)\s+(DEBIT|CREDIT)\s+₹\s?([\d,\.]+)$')
    when = re.compile(r'^(\d{1,2})[ :](\d{2})\s*(am|pm)', re.I)
    out = []
    for i, line in enumerate(lines):
        m = head.match(line)
        if not m:
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        t = when.match(nxt)
        stamp = f'{m[1]} {t[1]}:{t[2]} {t[3].upper()}' if t else f'{m[1]} 12:00 AM'
        d = datetime.strptime(stamp, '%b %d, %Y %I:%M %p')
        tid = re.search(r'Transaction ID\s*(\S+)', ' '.join(lines[i + 1:i + 3]))
        desc = m[2].strip()
        payee = re.sub(r'^(Paid to|Received from|Transfer to)\s+', '', desc)
        if desc.startswith('Transfer to'):
            payee = 'Bank a/c ' + payee[-4:]
        out.append(dict(date=d.strftime('%Y-%m-%d'), time=d.strftime('%H:%M') if t else '', payee=tidy(payee), remark='',
                        raw=desc, direction='out' if m[3] == 'DEBIT' else 'in', amount=float(m[4].replace(',', '')),
                        ref=tid.group(1) if tid else ''))
    if not out:
        print(f'  ! {os.path.basename(path)}: no PhonePe-style transactions found, skipped')
    return out


# ---------------------------------------------------------------- Excel / CSV statements
def read_grid(path):
    pd = need('pandas')
    ext = path.lower().rsplit('.', 1)[-1]
    if ext == 'xls':
        need('xlrd')
        return pd.read_excel(path, header=None, dtype=str, engine='xlrd')
    if ext == 'xlsx':
        need('openpyxl')
        return pd.read_excel(path, header=None, dtype=str, engine='openpyxl')
    for enc in ('utf-8-sig', 'latin-1'):
        try:
            return pd.read_csv(path, header=None, dtype=str, skip_blank_lines=False, on_bad_lines='skip',
                               engine='python', encoding=enc, sep=None)
        except UnicodeDecodeError:
            continue


def find_header(grid):
    for i in range(min(len(grid), 80)):
        cells = [str(c).strip().lower() for c in grid.iloc[i] if str(c) != 'nan']
        joined = ' | '.join(cells)
        if any(c.startswith(('date', 'txn date', 'transaction date', 'value date', 'tran date')) for c in cells) and \
           re.search(r'narration|description|particulars|details|remarks', joined):
            return i
    return None


def pick(cols, *names, avoid=()):
    for n in names:
        for i, c in enumerate(cols):
            if n in c and not any(a in c for a in avoid):
                return i
    return None


def money(v):
    s = re.sub(r'[^\d.\-]', '', str(v))
    try:
        return float(s) if s not in ('', '.', '-', 'nan') else 0.0
    except ValueError:
        return 0.0


def to_date(v):
    s = str(v).strip().split(' 00:00')[0]
    for f in ('%d/%m/%y', '%d/%m/%Y', '%d-%m-%Y', '%d-%m-%y', '%Y-%m-%d', '%d %b %Y', '%d-%b-%Y', '%d %b %y',
              '%d-%b-%y', '%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d %H:%M:%S', '%b %d, %Y'):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def read_table_statement(path):
    grid = read_grid(path)
    if grid is None:
        return []
    h = find_header(grid)
    if h is None:
        print(f'  ! {os.path.basename(path)}: could not find a header row with Date and Narration/Description, skipped')
        return []
    cols = [str(c).strip().lower() for c in grid.iloc[h]]
    c_date = pick(cols, 'txn date', 'transaction date', 'tran date', 'date', avoid=('value',))
    c_desc = pick(cols, 'narration', 'description', 'particulars', 'details', 'remarks')
    c_out = pick(cols, 'withdrawal', 'debit', 'dr amount', 'dr.')
    c_in = pick(cols, 'deposit', 'credit', 'cr amount', 'cr.')
    c_amt = pick(cols, 'amount', avoid=('withdrawal', 'deposit', 'debit', 'credit'))
    c_type = pick(cols, 'dr/cr', 'cr/dr', 'type')
    c_ref = pick(cols, 'chq', 'ref')
    out = []
    for i in range(h + 1, len(grid)):
        row = grid.iloc[i]
        d = to_date(row[c_date])
        if not d:
            continue
        raw = re.sub(r'\s+', ' ', str(row[c_desc])).strip()
        w = money(row[c_out]) if c_out is not None else 0.0
        c = money(row[c_in]) if c_in is not None else 0.0
        if c_out is None and c_in is None and c_amt is not None:
            a = money(row[c_amt])
            kind = str(row[c_type]).upper() if c_type is not None else ''
            if 'CR' in kind or (not kind and a > 0):
                c = abs(a)
            else:
                w = abs(a)
        if not w and not c:
            continue
        payee, remark = raw, ''
        up = raw.upper()
        if up.startswith('UPI'):
            parts = re.split(r'[-/]', raw)
            payee = parts[1] if len(parts) > 1 else raw
            remark = parts[-1] if len(parts) > 5 else ''
            if remark.upper() in ('UPI', 'PAYMENT', 'NA'):
                remark = ''
        elif up.startswith('NWD') or 'ATM' in up:
            payee, remark = 'ATM cash withdrawal', raw.split('-')[-1].title()
        elif 'CASH DEPOSIT' in up or up.startswith('BY CASH'):
            payee, remark = 'Cash deposit', raw.split('-')[-1].title()
        elif up.startswith(('NEFT', 'IMPS', 'RTGS', 'ACH')):
            parts = [p for p in re.split(r'[-/]', raw)[1:] if p.strip() and not re.match(r'^[A-Z]{4}0', p.strip())]
            payee = parts[0] if parts else raw
            remark = parts[-1] if len(parts) > 1 else ''
        ref = str(row[c_ref]).strip().lstrip('0') if c_ref is not None and str(row[c_ref]) != 'nan' else ''
        out.append(dict(date=d.strftime('%Y-%m-%d'), time='', payee=tidy(payee),
                        remark=remark.capitalize() if remark.isupper() else remark, raw=raw,
                        direction='out' if w else 'in', amount=round(w or c, 2), ref=ref))
    if not out:
        print(f'  ! {os.path.basename(path)}: no transactions found, skipped')
    return out


# ---------------------------------------------------------------- build
def collect(folder):
    user_rules = load_user_rules(folder)
    files = sorted(f for f in os.listdir(folder)
                   if f.lower().endswith(('.pdf', '.xls', '.xlsx', '.csv'))
                   and not f.lower().startswith(('my_categories', '~$', '.')))
    rows, seen, sources = [], set(), []
    for f in files:
        path = os.path.join(folder, f)
        acct = account_name(path)
        got = read_phonepe_pdf(path) if f.lower().endswith('.pdf') else read_table_statement(path)
        counts = {}
        for r in got:
            r['account'] = acct
            base = r['ref'] or hashlib.md5(f"{r['date']}|{r['raw']}|{r['amount']}|{r['direction']}".encode()).hexdigest()[:12]
            # same raw line twice on one day in one file is two payments; across files it's a duplicate
            counts[base] = counts.get(base, 0) + 1
            key = f'{acct}|{base}|{counts[base]}'
            if key in seen:
                continue
            seen.add(key)
            r['txn_id'] = hashlib.md5(key.encode()).hexdigest()[:10]
            r['category'] = categorize(r, user_rules)
            rows.append(r)
        if got:
            dates = sorted(r['date'] for r in got)
            sources.append(dict(file=f, account=acct, rows=len(got), first=dates[0], last=dates[-1]))
            print(f'  ✓ {f}: {len(got)} transactions ({dates[0]} to {dates[-1]}) → {acct}')
    rows.sort(key=lambda r: (r['date'], r['time']))
    return rows, sources


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    folder = os.path.abspath(args[0] if args else os.path.dirname(os.path.abspath(__file__)))
    print(f'Reading statements in {folder}')
    rows, sources = collect(folder)
    if not rows:
        sys.exit('No transactions found. Put .xls/.xlsx/.csv bank statements or PhonePe PDFs in the folder.')
    keep = ['date', 'time', 'account', 'payee', 'remark', 'category', 'direction', 'amount', 'txn_id']
    data = [{k: r[k] for k in keep} for r in rows]
    meta = dict(generated=datetime.now().strftime('%d %b %Y, %I:%M %p'), sources=sources, family=FAMILY_CATEGORY)
    html = TEMPLATE.replace('__DATA__', json.dumps(data, ensure_ascii=False)).replace('__META__', json.dumps(meta, ensure_ascii=False))
    out = os.path.join(folder, OUTPUT_NAME)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    spent = sum(r['amount'] for r in rows if r['direction'] == 'out' and r['category'] not in ('Between own accounts', FAMILY_CATEGORY))
    print(f'\n{len(rows)} transactions, ₹{spent:,.0f} spent (excluding own-account moves and {FAMILY_CATEGORY}).')
    print(f'Dashboard written to {out}')
    if '--no-open' not in sys.argv:
        webbrowser.open('file://' + out)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en-IN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spending dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
:root{--bg:#f7f6f3;--panel:#fff;--fg:#1f1e1c;--muted:#6f6c66;--line:#e6e3dc;--grid:#eeebe5;--pop:#fff;--shadow:0 6px 24px rgba(0,0,0,.12)}
@media (prefers-color-scheme:dark){:root{--bg:#191917;--panel:#232321;--fg:#ecebe7;--muted:#a3a09a;--line:#383733;--grid:#2e2d2a;--pop:#2c2b29;--shadow:0 6px 24px rgba(0,0,0,.5)}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.sp{max-width:1180px;margin:0 auto;padding:28px 20px 60px;display:flex;flex-direction:column;gap:22px}
h1{font:400 34px/1.15 Georgia,"Times New Roman",serif;margin:0}
.lede{font-size:18px;margin:10px 0 0;max-width:64ch}.lede b{font-weight:600}
.sub{color:var(--muted);font-size:13px;margin:6px 0 0}
.filters{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:12px 14px;background:var(--panel);border:1px solid var(--line);border-radius:14px;position:sticky;top:8px;z-index:10}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:inherit;font-size:13px;padding:5px 12px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
.chip:hover{border-color:var(--muted)}.chip[aria-pressed="true"]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.field{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--muted)}
.field input[type=date]{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:4px 6px;color-scheme:light dark}
.field input[type=checkbox]{width:15px;height:15px;accent-color:var(--fg)}
.reset{font:inherit;font-size:13px;background:none;border:0;color:var(--muted);text-decoration:underline;cursor:pointer;margin-left:auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;position:relative;overflow:hidden;min-width:0;container-type:inline-size}
.kpi{padding-left:24px}.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:var(--accent)}
.kl{font-size:13px;color:var(--muted)}.kv{font:400 30px/1.15 Georgia,serif;margin-top:6px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.kv.word{font-size:22px}
.kn{font-size:13px;color:var(--muted);margin-top:4px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px}
h2{font-size:18px;font-weight:600;margin:0}.hint{color:var(--muted);font-size:13px;margin:4px 0 12px}
.chart{position:relative}.chart svg{display:block;overflow:visible}.chart text{fill:var(--fg);font-family:inherit}
.axis text,.chart .tick-l{fill:var(--muted);font-size:12px}.axis path,.axis line{stroke:var(--line)}.gridl line{stroke:var(--grid)}.gridl path{display:none}
.mlabel{font-size:14px;font-weight:600}.chart .msub{fill:var(--muted);font-size:11px}.mtotal{font-size:13px;font-weight:600}
.hit{fill:transparent;cursor:pointer}.empty{color:var(--muted);padding:18px 0;margin:0}
.tip{position:absolute;left:0;top:0;pointer-events:none;background:var(--pop);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:9px;padding:8px 10px;font-size:13px;line-height:1.5;min-width:160px;max-width:290px;z-index:20;opacity:0;transition:opacity .15s}
.tip .th{font-weight:600;display:flex;justify-content:space-between;gap:12px;margin-bottom:2px}.tip .tr{display:flex;justify-content:space-between;gap:12px}.tip .tm{color:var(--muted)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex:none;vertical-align:baseline}
.keys{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted)}.keys li{display:flex;align-items:center}
.donutwrap{display:grid;grid-template-columns:auto 1fr;gap:18px;align-items:center}
@container (max-width:460px){.donutwrap{grid-template-columns:1fr;justify-items:center}.legend{width:100%}}
.dc1{font:400 22px Georgia,serif}.chart .dc2{fill:var(--muted);font-size:12px}
.legend{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px;min-width:0}
.legend button{all:unset;box-sizing:border-box;display:grid;grid-template-columns:auto 1fr auto auto;gap:10px;align-items:center;width:100%;padding:6px 8px;border-radius:7px;cursor:pointer;font-size:14px}
.legend button:hover,.legend button:focus-visible,.legend button[aria-pressed="true"]{background:var(--bg)}
.legend button[aria-pressed="true"]{outline:1px solid var(--line)}
.lshare{color:var(--muted);font-size:12px}.lamt{text-align:right;min-width:76px;font-variant-numeric:tabular-nums}
.tablewrap{overflow:auto;max-height:460px;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:12px;color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel)}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.small{display:block;color:var(--muted);font-size:12px}
.cat{display:inline-flex;align-items:center;white-space:nowrap;font-size:12px;padding:2px 8px 2px 6px;border-radius:999px;background:var(--bg);border:1px solid var(--line)}.cat .dot{width:8px;height:8px;margin-right:5px}
.caption{font-size:13px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.linkbtn{font:inherit;background:none;border:0;padding:0;color:var(--fg);text-decoration:underline;cursor:pointer}
details summary{cursor:pointer;font-weight:600}details ul{color:var(--muted);line-height:1.6;padding-left:1.2em}
@media (prefers-reduced-motion:reduce){.tip{transition:none}}
@media print{.filters{position:static}.tablewrap{max-height:none}}
</style>
</head>
<body>
<div class="sp">
  <header>
    <h1>Where the money went</h1>
    <p class="lede" id="lede"></p>
    <p class="sub" id="sources"></p>
  </header>

  <div class="filters">
    <div class="chips" id="presets" role="group" aria-label="Quick date ranges"></div>
    <div class="chips" id="accounts" role="group" aria-label="Account"></div>
    <label class="field">From <input type="date" id="start"></label>
    <label class="field">To <input type="date" id="end"></label>
    <label class="field" id="family-field"><input type="checkbox" id="family"> <span id="familyLabel"></span></label>
    <button class="reset" id="reset" type="button">Reset</button>
  </div>

  <section class="kpis">
    <div class="card kpi" style="--accent:#F97316"><div class="kl">Total spent</div><div class="kv" id="k-spent">—</div><div class="kn" id="k-payments"></div></div>
    <div class="card kpi" style="--accent:#3B82F6"><div class="kl">Average per day</div><div class="kv" id="k-perday">—</div><div class="kn" id="k-days"></div></div>
    <div class="card kpi" style="--accent:#EC4899"><div class="kl">Biggest category</div><div class="kv word" id="k-top">—</div><div class="kn" id="k-topamt"></div></div>
    <div class="card kpi" style="--accent:#22C55E"><div class="kl">Largest single payment</div><div class="kv" id="k-largest">—</div><div class="kn" id="k-largest-to"></div></div>
    <div class="card kpi" id="kpi-family" style="--accent:#A8A29E"><div class="kl" id="k-family-label"></div><div class="kv" id="k-family">—</div><div class="kn" id="k-family-note"></div></div>
    <div class="card kpi" style="--accent:#14B8A6"><div class="kl">Money received</div><div class="kv" id="k-in">—</div><div class="kn">not counting your own accounts</div></div>
  </section>

  <div class="row">
    <section class="card">
      <h2>Each month, by category</h2>
      <p class="hint">Point at a colour to see the amount.</p>
      <div class="chart" id="monthly"></div>
      <ul class="keys" id="keys"></ul>
    </section>
    <section class="card">
      <h2>Where it went</h2>
      <p class="hint">Tap a category to filter the payments list below.</p>
      <div class="chart donutwrap" id="categories"></div>
    </section>
  </div>

  <section class="card">
    <h2>Week by week</h2>
    <p class="hint">Weeks run Monday to Sunday. Point at a week for its breakdown.</p>
    <div class="chart" id="weekly" style="min-height:240px"></div>
    <div class="tablewrap" style="max-height:none">
      <table><thead><tr><th>Week</th><th class="num">Spent (₹)</th><th class="num">Payments</th><th>Biggest category</th></tr></thead><tbody id="weekly-rows"></tbody></table>
    </div>
  </section>

  <section class="card">
    <h2>Day by day</h2>
    <p class="hint">Each bar takes the colour of that day’s biggest category. Point at a day to see who you paid.</p>
    <div class="chips" style="margin-bottom:8px" role="group" aria-label="Bar scale">
      <button class="chip" data-scale="actual" aria-pressed="true" type="button">True scale</button>
      <button class="chip" data-scale="squash" aria-pressed="false" type="button">Squash big days</button>
    </div>
    <div class="chart" id="daily" style="min-height:220px"></div>
  </section>

  <section class="card">
    <h2>Payments</h2>
    <div class="caption" id="tx-caption"></div>
    <div class="tablewrap">
      <table><thead><tr><th>Date</th><th>Paid to</th><th>Category</th><th>Account</th><th class="num">Amount (₹)</th></tr></thead><tbody id="tx-rows"></tbody></table>
    </div>
  </section>

  <details>
    <summary>How this works</summary>
    <ul>
      <li>Built from the statement files listed at the top. Run the script again after adding or replacing files to refresh it.</li>
      <li>Categories come from the payee’s name and the note on each UPI payment. Add your own rules in my_categories.csv.</li>
      <li>Money moved between your own accounts is never counted, so nothing is counted twice.</li>
      <li>Payments to family are shown separately and only counted when you tick the box at the top.</li>
      <li>Cash withdrawals count as spending, since what the cash bought isn’t known.</li>
    </ul>
  </details>
</div>

<script>
const DATA = __DATA__;
const META = __META__;
(() => {
  const PALETTE = {
    'Food & Dining': '#F97316', 'Groceries': '#22C55E', 'Transport': '#3B82F6', 'Shopping': '#EC4899',
    'Home & Household': '#8B5CF6', 'Rent': '#14B8A6', 'Health & Care': '#EF4444', 'Subscriptions & Recharges': '#EAB308',
    'Entertainment': '#06B6D4', 'Services': '#B45309', 'Loans & EMI': '#0F766E', 'Cash withdrawals': '#64748B', 'People & other': '#84CC16'
  };
  PALETTE[META.family] = '#A8A29E';
  const EXTRA = ['#F43F5E', '#0EA5E9', '#D946EF', '#65A30D', '#FB923C', '#2DD4BF', '#A78BFA'];
  DATA.forEach((r) => { r.amount = +r.amount; if (!PALETTE[r.category] && r.category !== 'Between own accounts' && r.category !== 'Money in') PALETTE[r.category] = EXTRA[Object.keys(PALETTE).length % EXTRA.length]; });
  const CATS = Object.keys(PALETTE);
  const color = (c) => PALETTE[c] || '#9CA3AF';
  const inr = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 0});
  const inr2 = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 2});
  const fmt = (v) => inr.format(Math.round(+v || 0));
  const rs = (v) => '₹' + fmt(v);
  const short = (v) => v >= 100000 ? '₹' + d3.format('.3~')(v / 100000) + 'L' : v >= 1000 ? '₹' + d3.format('.3~')(v / 1000) + 'k' : rs(v);
  const parse = d3.utcParse('%Y-%m-%d'), iso = d3.utcFormat('%Y-%m-%d');
  const dFmt = d3.utcFormat('%-d %b'), dayFmt = d3.utcFormat('%a %-d %b');
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const dot = (c) => { const s = el('span', 'dot'); s.style.background = color(c); return s; };
  const chip = (c, label) => { const s = el('span', 'cat'); s.append(dot(c), document.createTextNode(label || c)); return s; };

  const dates = DATA.map((r) => r.date).sort();
  const MIN = dates[0], MAX = dates[dates.length - 1];
  const ACCOUNTS = [...new Set(DATA.map((r) => r.account))];
  const DEFAULTS = {start: MIN, end: MAX, acct: '', family: false, cat: '', squash: false};
  const S = {...DEFAULTS};

  // ---------- header text that doesn't change
  $('sources').textContent = META.sources.map((s) => `${s.account}: ${dFmt(parse(s.first))} – ${dFmt(parse(s.last))} ${s.last.slice(0, 4)}`).join(' · ')
    + ` · Built ${META.generated}. Amounts in ₹.`;
  $('familyLabel').textContent = 'Count ' + META.family.charAt(0).toLowerCase() + META.family.slice(1);
  $('k-family-label').textContent = META.family;
  if (!DATA.some((r) => r.category === META.family)) { $('kpi-family').hidden = true; $('family-field').hidden = true; }
  const PRESENT = new Set(DATA.map((r) => r.category));
  CATS.filter((c) => PRESENT.has(c)).forEach((c) => { const li = el('li'); li.append(dot(c), document.createTextNode(c)); $('keys').appendChild(li); });

  // ---------- presets: whole period, each month, last 14 / 7 days
  const presets = [['All dates', MIN, MAX]];
  d3.utcMonths(d3.utcMonth.floor(parse(MIN)), d3.utcDay.offset(parse(MAX), 1)).forEach((m) => {
    const a = iso(m), b = iso(d3.utcDay.offset(d3.utcMonth.offset(m, 1), -1));
    presets.push([d3.utcFormat('%B %Y')(m), a < MIN ? MIN : a, b > MAX ? MAX : b]);
  });
  presets.push(['Last 14 days', iso(d3.utcDay.offset(parse(MAX), -13)), MAX], ['Last 7 days', iso(d3.utcDay.offset(parse(MAX), -6)), MAX]);
  presets.forEach(([label, a, b]) => {
    const btn = el('button', 'chip', label); btn.type = 'button';
    btn.dataset.a = a < MIN ? MIN : a; btn.dataset.b = b;
    btn.onclick = () => set({start: btn.dataset.a, end: btn.dataset.b});
    $('presets').appendChild(btn);
  });
  [['All accounts', ''], ...ACCOUNTS.map((a) => [a, a])].forEach(([label, v]) => {
    const btn = el('button', 'chip', label); btn.type = 'button'; btn.dataset.v = v;
    btn.onclick = () => set({acct: v});
    $('accounts').appendChild(btn);
  });
  ['start', 'end'].forEach((k) => {
    const inp = $(k); inp.min = MIN; inp.max = MAX;
    inp.addEventListener('change', () => {
      if (!(inp.value && inp.validity.valid)) return;
      let {start, end} = S; if (k === 'start') start = inp.value; else end = inp.value;
      if (start > end) { if (k === 'start') end = start; else start = end; }
      set({start, end});
    });
    inp.addEventListener('blur', () => { inp.value = S[k]; });
  });
  $('family').onchange = (e) => set({family: e.target.checked});
  $('reset').onclick = () => set({...DEFAULTS});
  document.querySelectorAll('[data-scale]').forEach((b) => b.onclick = () => set({squash: b.dataset.scale === 'squash'}));

  function set(patch) { Object.assign(S, patch); render(); }

  // ---------- numbers
  function compute() {
    const inRange = DATA.filter((r) => r.date >= S.start && r.date <= S.end && (!S.acct || r.account === S.acct));
    const spending = inRange.filter((r) => r.direction === 'out' && r.category !== 'Between own accounts' && (S.family || r.category !== META.family));
    const total = d3.sum(spending, (r) => r.amount);
    const byCat = d3.rollups(spending, (v) => ({amount: d3.sum(v, (r) => r.amount), payments: v.length}), (r) => r.category)
      .map(([category, v]) => ({category, ...v, share: total ? Math.round(v.amount / total * 1000) / 10 : 0})).sort((a, b) => b.amount - a.amount);
    const days = Math.round((Date.parse(S.end) - Date.parse(S.start)) / 864e5) + 1;
    const biggest = spending.slice().sort((a, b) => b.amount - a.amount)[0];
    const byMonth = d3.rollups(spending, (v) => d3.sum(v, (r) => r.amount), (r) => r.date.slice(0, 7), (r) => r.category)
      .flatMap(([month, cs]) => cs.map(([category, amount]) => ({month, category, amount}))).sort((a, b) => a.month.localeCompare(b.month));
    const s = parse(S.start), e = parse(S.end);
    const weekly = d3.utcMonday.range(d3.utcMonday.floor(s), d3.utcDay.offset(e, 1)).map((w) => {
      const ws = iso(w), we = iso(d3.utcDay.offset(w, 6));
      const rows = spending.filter((r) => r.date >= ws && r.date <= we);
      const cats = d3.rollups(rows, (v) => d3.sum(v, (r) => r.amount), (r) => r.category).sort((a, b) => b[1] - a[1]);
      return {week: ws, from: ws < S.start ? S.start : ws, to: we > S.end ? S.end : we, amount: d3.sum(rows, (r) => r.amount), payments: rows.length,
              top: cats.length ? cats[0][0] : '', cats: cats.map(([category, amount]) => ({category, amount}))};
    });
    const daily = d3.utcDay.range(s, d3.utcDay.offset(e, 1)).map((d) => {
      const date = iso(d); const rows = spending.filter((r) => r.date === date);
      const cats = d3.rollups(rows, (v) => d3.sum(v, (r) => r.amount), (r) => r.category).sort((a, b) => b[1] - a[1]);
      return {date, amount: d3.sum(rows, (r) => r.amount), top: cats.length ? cats[0][0] : '', rows: rows.sort((a, b) => b.amount - a.amount)};
    });
    return {
      spending, byCat, byMonth, weekly, daily, total, days, biggest,
      moneyIn: d3.sum(inRange.filter((r) => r.direction === 'in' && r.category !== 'Between own accounts'), (r) => r.amount),
      family: d3.sum(inRange.filter((r) => r.direction === 'out' && r.category === META.family), (r) => r.amount)
    };
  }

  // ---------- tooltip
  function tip(host) {
    const t = el('div', 'tip'); host.appendChild(t);
    return {
      show(ev, lines) {
        t.replaceChildren();
        lines.forEach(([cls, text, c, right]) => {
          const d = el('div', cls); const l = el('span'); if (c) l.appendChild(dot(c)); l.append(document.createTextNode(text)); d.appendChild(l);
          if (right != null) d.appendChild(el('span', null, right)); t.appendChild(d);
        });
        t.style.opacity = 1;
        const r = host.getBoundingClientRect(), w = t.offsetWidth, h = t.offsetHeight;
        let x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
        if (x + w > r.width) x = Math.max(0, ev.clientX - r.left - w - 14);
        if (y + h > r.height + 30) y = Math.max(-10, ev.clientY - r.top - h - 14);
        t.style.transform = `translate(${x}px,${y}px)`;
      },
      hide() { t.style.opacity = 0; }
    };
  }
  const empty = (host, msg) => { host.replaceChildren(el('p', 'empty', msg)); };
  const toggleCat = (c) => set({cat: S.cat === c ? '' : c});

  // ---------- drawings
  function drawMonthly(C) {
    const host = $('monthly'); host.replaceChildren();
    if (!C.byMonth.length) return empty(host, 'No spending in these dates.');
    const months = [...new Set(C.byMonth.map((r) => r.month))].sort();
    const totals = new Map(months.map((m) => [m, d3.sum(C.byMonth.filter((r) => r.month === m), (r) => r.amount)]));
    const W = Math.max(280, host.clientWidth), rowH = 36, gap = 22, labelW = 84, endW = 84, H = months.length * (rowH + gap);
    const svg = d3.select(host).append('svg').attr('width', '100%').attr('height', H).attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', 'Spending each month by category');
    const x = d3.scaleLinear().domain([0, d3.max(totals.values()) || 1]).range([0, Math.max(40, W - labelW - endW)]);
    const t = tip(host);
    months.forEach((m, i) => {
      const md = parse(m + '-01'), first = m + '-01', last = iso(d3.utcDay.offset(d3.utcMonth.offset(md, 1), -1));
      const g = svg.append('g').attr('transform', `translate(0,${i * (rowH + gap) + gap / 2})`);
      g.append('text').attr('class', 'mlabel').attr('y', rowH / 2 - 7).attr('dy', '.35em').text(d3.utcFormat('%b %Y')(md));
      g.append('text').attr('class', 'msub').attr('y', rowH / 2 + 10).attr('dy', '.35em').text(`${dFmt(parse(S.start > first ? S.start : first))} – ${dFmt(parse(S.end < last ? S.end : last))}`);
      let acc = 0;
      C.byMonth.filter((r) => r.month === m).sort((a, b) => CATS.indexOf(a.category) - CATS.indexOf(b.category)).forEach((r) => {
        const x0 = x(acc); acc += r.amount;
        g.append('rect').attr('x', labelW + x0).attr('width', Math.max(0.8, x(acc) - x0 - 2)).attr('height', rowH).attr('rx', 5).style('fill', color(r.category)).style('cursor', 'pointer')
          .on('pointermove pointerdown', (ev) => t.show(ev, [['th', r.category, r.category], ['tr', 'Spent', null, rs(r.amount)], ['tm', `${Math.round(r.amount / totals.get(m) * 100)}% of ${d3.utcFormat('%B')(md)}`]]))
          .on('pointerleave', t.hide).on('click', () => toggleCat(r.category));
      });
      g.append('text').attr('class', 'mtotal').attr('x', labelW + x(acc) + 8).attr('y', rowH / 2).attr('dy', '.35em').text(rs(totals.get(m)));
    });
  }

  function drawCategories(C) {
    const host = $('categories'); host.replaceChildren();
    if (!C.byCat.length) return empty(host, 'No spending in these dates.');
    const box = el('div'); box.style.position = 'relative'; host.appendChild(box);
    const size = 210, R = size / 2, r0 = R * 0.6;
    const svg = d3.select(box).append('svg').attr('width', size).attr('height', size).attr('viewBox', `${-R} ${-R} ${size} ${size}`).attr('role', 'img').attr('aria-label', 'Share of spending by category');
    const arcs = d3.pie().value((r) => r.amount).sort(null).padAngle(0.014)(C.byCat);
    const arc = d3.arc().innerRadius(r0).outerRadius(R - 6).cornerRadius(3), arcH = d3.arc().innerRadius(r0 - 2).outerRadius(R).cornerRadius(3);
    const c1 = svg.append('text').attr('class', 'dc1').attr('text-anchor', 'middle').attr('y', 2);
    const c2 = svg.append('text').attr('class', 'dc2').attr('text-anchor', 'middle').attr('y', 22);
    const t = tip(box);
    const paths = svg.append('g').selectAll('path').data(arcs).join('path').attr('d', arc).style('fill', (a) => color(a.data.category)).style('cursor', 'pointer')
      .style('opacity', (a) => !S.cat || S.cat === a.data.category ? 1 : 0.28);
    const focus = (cat) => {
      paths.attr('d', (a) => a.data.category === cat ? arcH(a) : arc(a));
      const r = C.byCat.find((x) => x.category === cat);
      c1.text(rs(r ? r.amount : C.total)); c2.text(r ? `${r.share}% of total` : 'total spent');
    };
    focus(S.cat);
    paths.on('pointermove pointerdown', (ev, a) => { focus(a.data.category); t.show(ev, [['th', a.data.category, a.data.category], ['tr', 'Spent', null, rs(a.data.amount)], ['tr', 'Payments', null, String(a.data.payments)], ['tm', `${a.data.share}% of spending`]]); })
      .on('pointerleave', () => { focus(S.cat); t.hide(); }).on('click', (ev, a) => toggleCat(a.data.category));
    const ul = el('ul', 'legend');
    C.byCat.forEach((r) => {
      const b = el('button'); b.type = 'button'; b.setAttribute('aria-pressed', String(S.cat === r.category));
      b.append(dot(r.category), el('span', null, r.category), el('span', 'lshare', r.share + '%'), el('span', 'lamt', rs(r.amount)));
      b.onmouseenter = () => focus(r.category); b.onmouseleave = () => focus(S.cat); b.onclick = () => toggleCat(r.category);
      const li = el('li'); li.appendChild(b); ul.appendChild(li);
    });
    host.appendChild(ul);
  }

  function drawWeekly(C) {
    const host = $('weekly'); host.replaceChildren();
    const tb = $('weekly-rows'); tb.replaceChildren();
    if (!C.weekly.length) return empty(host, 'No weeks in these dates.');
    const W = Math.max(280, host.clientWidth), H = 240, m = {t: 24, r: 4, b: 40, l: 4};
    const x = d3.scaleBand().domain(C.weekly.map((r) => r.week)).range([m.l, W - m.r]).padding(0.3);
    const y = d3.scaleLinear().domain([0, d3.max(C.weekly, (r) => r.amount) || 1]).range([H - m.b, m.t]);
    const svg = d3.select(host).append('svg').attr('width', '100%').attr('height', H).attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', 'Spending each week by category');
    svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', H - m.b).attr('y2', H - m.b).style('stroke', 'var(--line)');
    const t = tip(host), tight = x.bandwidth() < 70;
    C.weekly.forEach((w) => {
      let acc = 0; const bars = [];
      w.cats.slice().sort((a, b) => CATS.indexOf(a.category) - CATS.indexOf(b.category)).forEach((sg, i) => {
        const y0 = y(acc); acc += sg.amount; const y1 = y(acc);
        bars.push(svg.append('rect').attr('x', x(w.week)).attr('width', x.bandwidth()).attr('y', y1).attr('height', Math.max(0, y0 - y1 - (i ? 1.5 : 0))).attr('rx', 3).style('fill', color(sg.category)));
      });
      const cx = x(w.week) + x.bandwidth() / 2;
      svg.append('text').attr('class', 'mtotal').attr('text-anchor', 'middle').attr('x', cx).attr('y', y(w.amount) - 7).text(tight ? short(w.amount) : rs(w.amount));
      svg.append('text').attr('class', 'tick-l').attr('text-anchor', 'middle').attr('x', cx).attr('y', H - m.b + 16).text(dFmt(parse(w.from)));
      if (!tight) svg.append('text').attr('class', 'tick-l').attr('text-anchor', 'middle').attr('x', cx).attr('y', H - m.b + 30).text('to ' + dFmt(parse(w.to)));
      svg.append('rect').attr('class', 'hit').attr('x', x(w.week) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', 0).attr('height', H - m.b)
        .on('pointermove pointerdown', (ev) => {
          bars.forEach((b) => b.style('opacity', 0.85));
          t.show(ev, [['th', `${dFmt(parse(w.from))} – ${dFmt(parse(w.to))}`, null, rs(w.amount)],
            ...(w.cats.length ? w.cats.map((c) => ['tr', c.category, c.category, rs(c.amount)]) : [['tm', 'No spending this week']]),
            ['tm', `${w.payments} payments`]]);
        })
        .on('pointerleave', () => { bars.forEach((b) => b.style('opacity', 1)); t.hide(); });
      const tr = tb.insertRow();
      tr.insertCell().textContent = `${dFmt(parse(w.from))} – ${dFmt(parse(w.to))}`;
      const a = tr.insertCell(); a.className = 'num'; a.textContent = fmt(w.amount);
      const n = tr.insertCell(); n.className = 'num'; n.textContent = w.payments;
      const c = tr.insertCell(); if (w.top) c.appendChild(chip(w.top)); else c.textContent = '—';
    });
  }

  function drawDaily(C) {
    const host = $('daily'); host.replaceChildren();
    document.querySelectorAll('[data-scale]').forEach((b) => b.setAttribute('aria-pressed', String((b.dataset.scale === 'squash') === S.squash)));
    if (!C.daily.length) return empty(host, 'No days in these dates.');
    const W = Math.max(280, host.clientWidth), H = 220, m = {t: 12, r: 6, b: 26, l: 50};
    const x = d3.scaleBand().domain(C.daily.map((r) => r.date)).range([m.l, W - m.r]).padding(0.22);
    const y = (S.squash ? d3.scaleSqrt() : d3.scaleLinear()).domain([0, d3.max(C.daily, (r) => r.amount) || 1]).nice(4).range([H - m.b, m.t]);
    const svg = d3.select(host).append('svg').attr('width', '100%').attr('height', H).attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', 'Spending each day');
    svg.append('g').attr('class', 'gridl').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)).tickFormat(''));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(6).tickFormat(short)).call((g) => g.select('.domain').remove());
    const every = Math.max(1, Math.ceil(48 / x.step()));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickSize(0).tickPadding(8).tickValues(C.daily.map((r) => r.date).filter((_, i) => i % every === 0)).tickFormat((v) => dFmt(parse(v))));
    const t = tip(host);
    const bars = svg.append('g').selectAll('rect').data(C.daily).join('rect').attr('x', (r) => x(r.date)).attr('width', x.bandwidth())
      .attr('y', (r) => y(r.amount)).attr('height', (r) => Math.max(0, y(0) - y(r.amount))).attr('rx', Math.min(3, x.bandwidth() / 3)).style('fill', (r) => r.top ? color(r.top) : 'var(--grid)');
    svg.append('g').selectAll('rect').data(C.daily).join('rect').attr('class', 'hit').attr('x', (r) => x(r.date) - x.step() * x.paddingInner() / 2).attr('width', x.step()).attr('y', m.t).attr('height', H - m.b - m.t)
      .on('pointermove pointerdown', (ev, r) => {
        bars.style('opacity', (b) => b.date === r.date ? 1 : 0.45);
        t.show(ev, [['th', dayFmt(parse(r.date)), null, rs(r.amount)],
          ...(r.rows.length ? r.rows.slice(0, 6).map((p) => ['tr', p.remark ? `${p.payee} · ${p.remark}` : p.payee, p.category, rs(p.amount)]) : [['tm', 'No spending']]),
          ...(r.rows.length > 6 ? [['tm', `+ ${r.rows.length - 6} more`]] : [])]);
      })
      .on('pointerleave', () => { bars.style('opacity', 1); t.hide(); });
  }

  function drawTable(C) {
    const cap = $('tx-caption'); cap.replaceChildren();
    const rows = C.spending.filter((r) => !S.cat || r.category === S.cat).sort((a, b) => (b.date + b.time).localeCompare(a.date + a.time));
    cap.appendChild(el('span', null, `${rows.length} payment${rows.length === 1 ? '' : 's'}, newest first`));
    if (S.cat) { const b = el('button', 'linkbtn', 'Show all categories'); b.type = 'button'; b.onclick = () => set({cat: ''}); cap.append(chip(S.cat, S.cat + ' only'), b); }
    const tb = $('tx-rows'); tb.replaceChildren();
    if (!rows.length) { const td = tb.insertRow().insertCell(); td.colSpan = 5; td.className = 'small'; td.textContent = 'No payments in these dates.'; return; }
    rows.forEach((r) => {
      const tr = tb.insertRow();
      const d = tr.insertCell(); d.append(document.createTextNode(dayFmt(parse(r.date)))); if (r.time) d.appendChild(el('span', 'small', r.time));
      const p = tr.insertCell(); p.append(document.createTextNode(r.payee)); if (r.remark) p.appendChild(el('span', 'small', r.remark));
      tr.insertCell().appendChild(chip(r.category));
      const a = tr.insertCell(); a.className = 'small'; a.style.display = 'table-cell'; a.textContent = r.account;
      const n = tr.insertCell(); n.className = 'num'; n.textContent = inr2.format(r.amount);
    });
  }

  function render() {
    const C = compute();
    // controls reflect state
    $('start').value = S.start; $('end').value = S.end; $('family').checked = S.family;
    document.querySelectorAll('#presets .chip').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.a === S.start && b.dataset.b === S.end)));
    document.querySelectorAll('#accounts .chip').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === S.acct)));
    // headline
    const lede = $('lede'); lede.replaceChildren();
    const b = (t) => el('b', null, t), txt = (t) => document.createTextNode(t);
    if (!C.spending.length) lede.append(txt('No spending between the dates you picked. Try a wider range.'));
    else {
      const top = C.byCat[0];
      lede.append(txt(`From ${dFmt(parse(S.start))} to ${d3.utcFormat('%-d %b %Y')(parse(S.end))}, you spent `), b(rs(C.total)), txt(' across '), b(String(C.spending.length)),
        txt(' payments. '), b(top.category), txt(` was the biggest slice, at ${Math.round(top.share)}% of the total, and the single biggest payment was `),
        b(rs(C.biggest.amount)), txt(' to '), b(C.biggest.payee), txt('.'));
    }
    $('k-spent').textContent = rs(C.total); $('k-payments').textContent = `${C.spending.length} payments`;
    $('k-perday').textContent = rs(C.days > 0 ? C.total / C.days : 0); $('k-days').textContent = `over ${C.days} days`;
    $('k-top').textContent = C.byCat[0] ? C.byCat[0].category : '—'; $('k-topamt').textContent = C.byCat[0] ? rs(C.byCat[0].amount) : '';
    $('k-largest').textContent = C.biggest ? rs(C.biggest.amount) : '—'; $('k-largest-to').textContent = C.biggest ? 'to ' + C.biggest.payee : '';
    $('k-family').textContent = rs(C.family); $('k-family-note').textContent = S.family ? 'Counted in spending' : 'Not counted as spending';
    $('k-in').textContent = rs(C.moneyIn);
    drawMonthly(C); drawCategories(C); drawWeekly(C); drawDaily(C); drawTable(C);
  }

  let timer; window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(render, 150); });
  render();
})();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    main()
