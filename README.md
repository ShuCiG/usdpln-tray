# usdpln-tray

Monitors the USD/PLN exchange rate. Shows it in the Windows system tray, logs
every reading to a local SQLite database, and raises alerts on sharp moves or
threshold crossings. Data from Yahoo Finance (live spot rate).

## Install and run (Windows)

```bat
pip install -r requirements.txt
python tray.py
```

The rate refreshes every minute. Each sample is logged to `rates.db` (SQLite,
created next to `tray.py`). **Left-click** the icon for a Stocks-style details
popup (symbol, change, OHLC, intraday sparkline); **right-click** for the menu
(Rate chart / Refresh / Exit).

## Rate chart

The tray menu has a **Rate chart** item that opens a window with the rate
history from `rates.db`. The window has two dropdowns:

- **Period** — `1 hour`, `24 hours`, `7 days`, `30 days`, `1 year`.
- **Type** — `line`, `scatter`, `step`.

The aggregation granularity is auto-picked from the period:

| Period | Aggregation |
|--------|-------------|
| 1 hour | 1-minute average |
| 24 hours | 30-minute average |
| 7 days | 4-hour average |
| 30 days | daily average |
| 1 year | daily average |

Buckets with no data (weekends, downtime) are forward-filled from the last
known rate so the line stays continuous instead of collapsing into a single
dot when the wall-clock window sits entirely on a weekend.

The chart uses the same dark Stocks-style palette as the tooltip popup —
line color is green or red depending on whether the period closed above or
below its starting value, with a dashed reference line at that starting
value. The bottom toolbar provides Home / Pan / Zoom / Save (PNG). The
chart can also be opened standalone:

```bat
python chart.py
```

## Configuration

Copy `config.example.json` to `config.json` and edit it. If `config.json` is
absent the app runs with built-in defaults (email off, desktop notifications
on).

```json
{
  "refresh_interval": 60,
  "alerts": {
    "spike_pct": 1.0,
    "spike_window_seconds": 3600,
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

- `refresh_interval` — seconds between polls (60 = once a minute).
- `spike_pct` — alert when the rate moves at least this percent over the
  configured window. Set to `0` to disable spike alerts.
- `spike_window_seconds` — comparison window for `spike_pct`. The current rate
  is compared against the most recent sample at or before
  `now - spike_window_seconds` (default `3600` = 1 hour). With minute polling
  this gives `spike_pct` a fixed time-based meaning instead of "since the last
  poll".
- `threshold_high` / `threshold_low` — alert when the rate crosses above the
  high bound or below the low bound. `null` disables that bound.
- `desktop_notifications` — show Windows toast alerts (tray mode only).
- `email` — see below.

Each fired alert is also recorded in the `alerts` table of `rates.db`.

## Alerts

An alert fires when:

- the rate moved by at least `spike_pct` percent over the last
  `spike_window_seconds` (compared to the rate from that long ago), or
- the rate crossed above `threshold_high` between the previous reading and
  the current one, or
- the rate crossed below `threshold_low` between the previous reading and
  the current one.

Threshold alerts fire once per crossing — a rate that stays past a bound is not
re-alerted on every poll.

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

## Standalone executable (PyInstaller)

Build a single Windows `.exe` that runs without Python installed.

```bat
pip install pyinstaller
build.bat
```

Output: `dist\usdpln-tray\usdpln-tray.exe` plus a folder of dependencies
(`--onedir` layout — fast startup, fewer antivirus false positives than
`--onefile`). To distribute, zip the whole `dist\usdpln-tray\` folder.

At runtime the `.exe` looks for `config.json` and writes `rates.db` next to
itself, so drop the bundled folder anywhere and put your `config.json`
beside the `.exe`. `config.example.json` is bundled inside the build as a
template.

Notes:
- The tray menu's **Rate chart** and the **left-click details popup** both
  work from the bundled `.exe`: the same binary re-launches itself with
  internal `--chart` / `--tooltip` flags.
- Headless mode (`--headless`) is not exposed from the build — the bundle
  is built with `--windowed`, which has no console. Use the Python script
  or the Docker container for headless deployments.
- Windows Defender occasionally flags PyInstaller bundles as false
  positives; if needed, sign the executable or add an exclusion.

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
