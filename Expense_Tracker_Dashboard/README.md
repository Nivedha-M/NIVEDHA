# Expense Tracker Dashboard

Turn your bank statements into a colourful, interactive spending dashboard with one command.

Put your statements (Excel, CSV or PhonePe PDF) in a folder and run the script. It sorts every payment into a category and writes `dashboard.html`. When you add next month's statement, run it again and the dashboard updates.

![Dashboard overview](dashboard_screenshot.png)

## Features

- **Monthly spending by category**: stacked bars for each month, with the amount shown when you point at a colour.
- **Where it went**: a ring chart and a ranked list of categories with amounts and percentages. Click a category to filter the payments list.
- **Weekly summary**: a Monday-to-Sunday chart plus a table with each week's total, number of payments and biggest category.
- **Day by day**: daily bars coloured by that day's biggest category, with a tooltip listing who you paid. A "Squash big days" button keeps one large payment from flattening the rest of the chart.
- **Filters**: quick date ranges (each month, last 7 or 14 days), From/To date pickers, and one button per account.
- **Headline figures**: total spent, average per day, biggest category, largest payment and money received.
- **Automatic categories** from the payee's name and the note on each UPI payment. For example, "5th nov rent" goes to Rent and "petrol" goes to Transport.
- **No double counting**: money moved between your own accounts is left out, and the same payment in two overlapping exports is only counted once.
- **Works on a phone or narrow window**, and follows your system's light or dark mode.

## Requirements

- Python 3.8 or newer
- These packages, installed once:

```bash
pip3 install pandas xlrd openpyxl pdfplumber
```

`xlrd` reads old `.xls` files, `openpyxl` reads `.xlsx`, and `pdfplumber` reads PhonePe PDFs. You can skip any you don't need.

## Quick start

1. Put `spending_dashboard.py` and your statement files in one folder.
2. Open Terminal in that folder and run:

```bash
python3 spending_dashboard.py
```

3. `dashboard.html` is created in the same folder and opens in your browser.

To read statements from another folder:

```bash
python3 spending_dashboard.py /path/to/statements
```

To build the dashboard without opening the browser:

```bash
python3 spending_dashboard.py --no-open
```

The script lists each file it read, how many transactions it found and the dates they cover:

```
Reading statements in /Users/you/Expense Tracker Dashboard
  ✓ sbi_5678_sample_statement.xlsx: 211 transactions (2026-09-01 to 2026-11-30) → SBI

211 transactions, ₹65,373 spent (excluding own-account moves and Transfers to family).
Dashboard written to /Users/you/Expense Tracker Dashboard/dashboard.html
```

## Supported statement files

| Type | Notes |
|---|---|
| `.xls`, `.xlsx`, `.csv` bank statements | Any export with a **Date** column, a **Narration / Description / Particulars** column, and either **Withdrawal + Deposit**, **Debit + Credit**, or one **Amount** column. Tested with HDFC's format. Header and summary rows around the table are skipped. |
| PhonePe statement PDF | The "Transaction Statement" PDF you can download from the PhonePe app. |

Bank PDF statements (not PhonePe) aren't read. For those, download the Excel or CSV version from internet banking instead.

### Name your files after the account

The account name shown on the dashboard comes from the file name:

| File name | Shown as |
|---|---|
| `hdfc_1234_statement.csv` | HDFC ••1234 |
| `sbi_5678_statement.xlsx` | SBI |
| `sbi_phonepe_oct.pdf` | SBI (PhonePe) |
| `icici_9012_nov.xls` | ICICI ••9012 |

Include the bank name, and the last 4 digits of the account between underscores.

### Updating with new statements

Add the new statement to the folder and run the script again. You can keep old files: overlapping payments are only counted once. When a statement has reference numbers, those are used to spot duplicates. Otherwise the date, description and amount are used.

## Categories

These are the built-in categories:

Food & Dining · Groceries · Transport · Shopping · Home & Household · Rent · Loans & EMI · Health & Care · Subscriptions & Recharges · Entertainment · Services · Cash withdrawals · People & other

Three groups are handled separately:

- **Between own accounts**: transfers between your own accounts. These are never counted as spending or as money received.
- **Family transfers**: payments to a family member you name. They appear in their own card and are counted as spending only when you tick the box on the dashboard.
- **Money in**: salary, deposits and other money you receive.

Payments to individuals whose purpose can't be worked out go into **People & other**.

### Adding your own rules

Create `my_categories.csv` in the same folder as your statements:

```csv
keyword,category
RAMESH,Food & Dining
GYM,Health & Care
PETS CORNER,Pets
```

Any payment whose payee or UPI note contains the keyword gets that category. Matching ignores upper and lower case. Your rules are checked before the built-in ones. You can also make up new categories, as with "Pets" above, and they get their own colour.

## Settings

Edit these at the top of `spending_dashboard.py`:

```python
# Names on your own accounts: money moved between them is never counted as spending.
OWN_ACCOUNT_NAMES = ['YOUR NAME']

# People whose transfers are kept apart (shown, but only counted when you switch them on).
FAMILY = {'PARTNER NAME': 'Partner'}
FAMILY_CATEGORY = 'Transfers to family'

# Built-in keyword rules, checked in order.
RULES = [ ... ]

OUTPUT_NAME = 'dashboard.html'
```

- `OWN_ACCOUNT_NAMES`: use the name as it appears on your statements, such as the account holder name on UPI transfers.
- `FAMILY`: leave it as `{}` if you don't want family transfers kept apart. The checkbox and card then disappear from the dashboard.
- `RULES`: add keywords to any category, or add new `('Category', ['KEYWORD', ...])` entries.

## Privacy

- Your statements are read only on your computer. Nothing is uploaded.
- `dashboard.html` contains your transactions, so treat it like a bank statement.
- The dashboard loads its charting library ([d3](https://d3js.org)) from a public CDN when you open it, so it needs an internet connection. No transaction data is sent there.

## Try it with sample data

`sbi_5678_sample_statement.xlsx` contains made-up transactions for September to November 2026. Run the script in this folder to see the dashboard without using your own data.

## Project files

```
spending_dashboard.py           the script (reader, categoriser and dashboard template)
my_categories.csv               optional: your own category rules
*.xls / *.xlsx / *.csv / *.pdf  your statements
dashboard.html                  generated: open in any browser
```

## Troubleshooting

| Message | What to do |
|---|---|
| `Missing Python package "xlrd"` (or another package) | Run the `pip3 install` line from Requirements. |
| `could not find a header row with Date and Narration/Description` | The file's columns use different names. Open it, check the header names, and download the statement as Excel or CSV from your bank. |
| `no PhonePe-style transactions found` | The PDF isn't a PhonePe statement. Use your bank's Excel or CSV export instead. |
| A payment is in the wrong category | Add a line for it to `my_categories.csv`. |
| Charts don't appear | Check your internet connection, since the charting library loads online. |
