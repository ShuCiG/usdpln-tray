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
created next to `tray.py`). Right-click the icon for the menu
(Rate chart / Refresh / Exit).

## Rate chart

The tray menu has a **Rate chart** item that opens a window with the rate
history from `rates.db`. The window has two dropdowns:

- **Period** — `1 hour`, `24 hours`, `7 days`, `30 days`, `1 year`.
- **Type** — `line`, `scatter`, `step`.

The aggregation granularity is auto-picked from the period:

| Period | Aggregation |
|--------|-------------|
| 1 hour | raw (every sample) |
| 24 hours | 4-hour average |
| 7 days | 4-hour average |
| 30 days | daily average |
| 1 year | daily average |

The matplotlib navigation toolbar at the bottom of the window allows pan,
zoom, and save-to-PNG. The chart can also be opened standalone:

```bat
python chart.py
```

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

The DB and config paths can also be set via environment variables:
`USDPLN_DB_PATH` and `USDPLN_CONFIG_PATH`. Both default to the file alongside
`tray.py`.

## Docker (headless deployment)

The repo ships a `Dockerfile` and `docker-compose.yml` that run the headless
poller in a Linux container — useful for keeping the rate logger and email
alerts up on a VPS or NAS, where Windows tray / chart features are not
applicable. `restart: unless-stopped` makes the container self-recover on
crashes and after host reboots.

```bash
# One-time: prepare config.json next to docker-compose.yml.
cp config.example.json config.json
# edit config.json: fill SMTP credentials, set email.enabled to true

docker compose up -d --build
docker compose logs -f
```

Layout:

- `requirements.txt` uses `sys_platform == "win32"` markers, so the container
  installs only `requests` and skips the Windows-only packages (`pystray`,
  `Pillow`, `windows-toasts`, `matplotlib`).
- The container mounts two volumes:
  - `./docker-data` → `/data` — persisted SQLite DB (`rates.db` + alerts).
  - `./config.json` → `/config/config.json` (read-only) — runtime config.
- Inside the container `tray.py --headless` is run with
  `USDPLN_DB_PATH=/data/rates.db` and `USDPLN_CONFIG_PATH=/config/config.json`.

To stop the service: `docker compose down`. The DB and config stay on the
host.
