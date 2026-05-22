# usdpln-tray

Monitors the USD/PLN exchange rate. Shows it in the Windows system tray, logs
every reading to a local SQLite database, and raises alerts on sharp moves or
threshold crossings. Data from the NBP API (National Bank of Poland).

## Install and run (Windows)

```bat
pip install -r requirements.txt
python tray.py
```

The rate refreshes every hour. Each sample is logged to `rates.db` (SQLite,
created next to `tray.py`). Right-click the icon for the menu (Refresh / Exit).

## Configuration

Copy `config.example.json` to `config.json` and edit it. If `config.json` is
absent the app runs with built-in defaults (email off, desktop notifications
on).

```json
{
  "refresh_interval": 3600,
  "alerts": {
    "spike_pct": 1.0,
    "threshold_high": 3.75,
    "threshold_low": null
  },
  "desktop_notifications": true,
  "email": {
    "enabled": false,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "username": "you@gmail.com",
    "password": "",
    "from_addr": "you@gmail.com",
    "to_addr": "you@gmail.com"
  }
}
```

- `refresh_interval` — seconds between polls (3600 = 1 hour).
- `spike_pct` — alert when the rate moves at least this percent vs the previous
  reading. Set to `0` to disable spike alerts.
- `threshold_high` / `threshold_low` — alert when the rate crosses above the
  high bound or below the low bound. `null` disables that bound.
- `desktop_notifications` — show Windows toast alerts (tray mode only).
- `email` — see below.

Each fired alert is also recorded in the `alerts` table of `rates.db`.

## Alerts

An alert fires when, compared to the previous reading:

- the rate moved by at least `spike_pct` percent, or
- the rate crossed above `threshold_high`, or
- the rate crossed below `threshold_low`.

Threshold alerts fire once per crossing — a rate that stays past a bound is not
re-alerted every hour.

## Email alerts (Gmail)

Email uses SMTP over SSL. For Gmail:

1. Enable 2-Step Verification on the Google account.
2. Create a 16-character **App Password** (Google Account → Security → App
   passwords).
3. In `config.json`, set `email.enabled` to `true`, fill `username`,
   `from_addr`, `to_addr`, and paste the app password into `password`.

> The password is stored in plaintext in `config.json`. That file is listed in
> `.gitignore` so it is never committed — keep it that way.

## Headless mode

Run without a tray icon — useful for a background data logger / email alerter.
In headless mode there are **no desktop notifications**; alerts go out by email
only (if email is enabled).

```bat
python tray.py --headless
```

- No console window (background): `pythonw tray.py --headless`
- Auto-start at logon: create a Windows Task Scheduler task that runs the
  `pythonw` command above at logon.

Use `--config PATH` to point at a config file other than `config.json`.
