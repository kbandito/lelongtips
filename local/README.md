# Running the scrape from your own PC

## Why this exists

Lelongtips hides prices, exact dates and addresses from anyone who is not
logged in. Its login is tied to the network it was created on: the same
session cookie that works in your browser is rejected from a server abroad.
We confirmed that with a plain HTTP client and again with a full Chromium
browser running on a US machine — both were served guest content.

So the scrape has to run from your connection. Everything after it does not,
so this only does the scrape: it saves a snapshot and pushes it. GitHub picks
that up and does the rest — rebuilding the database, regenerating the
dashboard and sending the Telegram alert.

## One-time setup

1. Install Python 3.11 or newer from python.org. Tick **"Add Python to PATH"**
   during installation.
2. Install Git from git-scm.com.
3. Open Command Prompt and clone the repository:

       git clone https://github.com/kbandito/lelongtips.git
       cd lelongtips
       pip install -r src/requirements.txt

   The clone is large (about 1 GB) because it carries every past snapshot.

## Each run

1. Log in to lelongtips.com.my in Chrome.
2. Press F12 → **Application** → **Cookies** → `https://www.lelongtips.com.my`.
3. Click **`lt_session`**, untick "Show URL-decoded", and copy the whole value
   from the panel at the bottom — not from the table column, which is
   truncated.
4. In Command Prompt:

       set LELONGTIPS_COOKIE=paste_the_value_here
       local\run_scrape.bat

The scrape takes roughly 35 minutes. It is polite to the site by design:
one page every two seconds.

## Checking it worked

The run prints a summary. The line to look for is the masked-price warning:

- No warning → prices came through and the session worked.
- "100% have a masked price" → the cookie was not accepted. Log in again,
  copy a fresh `lt_session`, and retry.

To test the cookie on its own without a full scrape:

    python src\check_session.py "%LELONGTIPS_COOKIE%"

It reports whether the site recognises you and how many prices are visible.

## Making it automatic

Windows Task Scheduler can run `local\run_scrape.bat` every three days.
The catch is the cookie: it expires, and refreshing it means logging in
through a browser by hand. Until that is automated, expect to refresh it
every week or two — the scrape fails loudly and sends a Telegram alert when
the session dies, so you will know rather than quietly collecting nothing.
