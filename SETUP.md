# Setup Guide

Step-by-step setup for [Product Hunter](README.md). Follow it once, top to
bottom, and the bot runs itself from then on.


## What you need

- A Google account (free)
- A GitHub account (free)
- About 30 minutes, once

You do **not** need to know how to code. You just follow the steps.

---

## Step 1 — Make the Google Sheet

1. Go to [sheets.google.com](https://sheets.google.com) and make a new sheet.
2. Rename it exactly: **`Product Hunter`**
3. Leave it empty. The script builds the tabs itself.

---

## Step 2 — Get a Google robot account

This gives the script permission to write into your sheet.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **New Project** → name it `hunter` → Create.
2. In the search bar type **Google Sheets API** → click it → **Enable**.
   Then do the same for **Google Drive API**. You need **both**.
   > The script finds your sheet *by name*, and searching by name is a Drive
   > operation. With Sheets alone you get a `403 ... Drive API has not been used`
   > error that looks like a sharing problem but is not.
3. Left menu → **Credentials** → **Create credentials** → **Service account**.
   - Name it `hunter-bot` → Create → Done.
4. Click the service account you just made → **Keys** tab → **Add key** → **Create new key** → **JSON** → Create.
   - A `.json` file downloads. **Keep it, you need it in Step 4.**
5. Open that JSON file in Notepad. Find the line that says `"client_email"`.
   Copy that email address (it looks like `hunter-bot@hunter-123.iam.gserviceaccount.com`).
6. Go back to your Google Sheet → **Share** → paste that email → give it **Editor** → Send.

> If you skip 5 and 6 the script cannot see your sheet. This is the step people miss.

---

## Step 3 — Put the code on GitHub

1. Go to [github.com/new](https://github.com/new). Name it `product-hunter`. Set it to **Private**. Create.
2. Click **uploading an existing file**.
3. Drag in these files:
   - `hunter.py`
   - `config.py`
   - `brands.txt`
   - `requirements.txt`
   - `selftest.py`
   - `README.md`
4. Commit.
5. Now upload the workflow file. Click **Add file** → **Create new file**.
   In the filename box type exactly: `.github/workflows/daily.yml`
   Then paste the contents of the `daily.yml` file. Commit.

---

## Step 4 — Give GitHub your Google key

1. In your repo: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. Name: `GOOGLE_CREDENTIALS`
3. Secret: open the JSON file from Step 2 and paste **the whole thing**, from the
   first `{` to the last `}`.
4. Add secret.

---

## Step 5 — Run it

1. Go to the **Actions** tab in your repo.
2. Click **Daily product hunt** on the left.
3. Click **Run workflow** → **Run workflow**.
4. Wait. It takes 1–3 hours the first time. Click into the run to watch the log.

After that it runs by itself every day at 02:00 UTC (07:00 Pakistan time).
Change the time in `.github/workflows/daily.yml` on the `cron:` line.

---

## Changing the rules

Open `config.py`. Everything is in there and labelled:

| I want to... | Change this |
|---|---|
| Get more/fewer products | `TARGET_PRODUCTS_PER_DAY` |
| Change the max eBay price | `max_price` inside `MARKETS` |
| Change the profit rule | `MIN_ROI` (0.50 = 50%) |
| Require more AliExpress orders | `ALI_MIN_ORDERS` |
| Search different products | `SEARCH_TERMS` — add as many as you like |
| Be stricter about "sells daily" | `MIN_DISTINCT_SALE_DAYS` |

**Add more `SEARCH_TERMS`.** This is the single biggest lever on how many
products you get. 40 terms is a starting point, not a limit. Go to 150.

---

## When it stops finding things

**"0 products passed"** — your rules are too tight for those search terms.
Add more `SEARCH_TERMS` first. Then try lowering `MIN_DISTINCT_SALE_DAYS` to 7.

**"Nothing came back. eBay may be blocking you"** — free scraping got shut out.
Fix it in one line:

1. Make a free account at [apify.com](https://apify.com) ($5 free credit monthly).
2. Copy your API token from **Settings → API & Integrations**.
3. Add it as a second GitHub secret named `APIFY_TOKEN`.
4. In `config.py` set `SOURCE_MODE = "apify"`.

Now it uses paid data instead of scraping. Roughly $2–6 per day at 100 products.
`SOURCE_MODE = "auto"` (the default) tries free first and only pays when free fails.

**Products repeat** — they shouldn't. The `_seen` tab in your sheet remembers
everything already delivered. Don't delete that tab. To start fresh, clear it.

---

## That's it

Setup is done. See the [main README](README.md) for how the bot works, what
each config option does, and how to keep it running well.
