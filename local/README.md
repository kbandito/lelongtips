# Running the scrape from your own PC

## Why this exists

Lelongtips hides prices, exact auction dates and street addresses from anyone
who is not logged in, and its login is tied to the network that created it.
The same session cookie that works in your browser is refused from a server
abroad. That was confirmed twice: once with a plain HTTP client, and again
with a full Chromium browser (Malaysian locale and timezone) running on a US
machine. Both were served masked prices.

So the scrape has to run from your connection. Nothing after it does, so this
only scrapes: it saves a snapshot and pushes it to GitHub, which rebuilds the
database, regenerates the dashboard and sends the Telegram alert as before.

## One-time setup

1. Install **Python** from python.org. Tick **"Add Python to PATH"** during
   installation — the script cannot find Python without it.
2. Install **Git** from git-scm.com.
3. Open Command Prompt and run:

       git clone --depth 1 https://github.com/kbandito/lelongtips.git
       cd lelongtips

   `--depth 1` skips years of history and saves several gigabytes. The
   download is still large because the repository carries every past snapshot.

4. Copy `local\cookie.txt.example` to `local\cookie.txt`.

## Each run

1. Log in to lelongtips.com.my in Chrome.
2. Press **F12** → **Application** → **Cookies** → `https://www.lelongtips.com.my`.
3. Click **`lt_session`**. Untick **"Show URL-decoded"**. Copy the whole value
   from the panel at the bottom — not from the table column, which is cut off.
   It is several hundred characters and starts with `eyJpdiI6`.
4. Paste it into `local\cookie.txt`, replacing whatever is there, and save.
5. Double-click `local\run_scrape.bat`.

The cookie goes in a file rather than a command because Windows mangles the
`%` characters it contains when expanding variables. `cookie.txt` is ignored
by Git, so it is never uploaded.

The script checks your login before starting, so a dead cookie costs you a few
seconds rather than a wasted half hour. The scrape itself takes about 35
minutes — one page every two seconds, to stay polite to the site. You can use
the PC normally while it runs.

## What you should see

    Checking your login...
      signed in as        : Tan Hui Sin
      real prices         : 12  ['RM196,830', ...]
    Login OK. Scraping now - this takes about 35 minutes.

If instead it says **NOT SIGNED IN**, the cookie has expired. Log in again,
copy a fresh one, and rerun. Sessions typically last days to a couple of
weeks.

## Checking the cookie on its own

    python src\check_session.py

It reports whether the site recognises you and how many prices are visible,
without scraping anything.

## Making it automatic

Windows Task Scheduler can run `local\run_scrape.bat` on a schedule. The
snag is the cookie: it expires, and refreshing it means logging in through a
browser by hand. Until that is automated, expect to refresh it every week or
two.

You do not have to do this at all to keep the project alive. GitHub keeps
scraping every three days on its own and still sends Telegram alerts; it just
cannot see prices. Run this when you want a priced refresh.
