# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (Windows gets all; Linux/Docker skips pystray/Pillow/windows-toasts/matplotlib)
pip install -r requirements.txt

# Run as Windows tray icon
python tray.py

# Run headless (cross-platform, email alerts only, no desktop notifications)
python tray.py --headless

# Point at a custom config
python tray.py --config /path/to/config.json

# Open the chart window standalone
python chart.py --db /path/to/rates.db

# Docker headless deployment
cp config.example.json config.json   # then fill SMTP creds
docker compose up -d --build
docker compose logs -f
```

No test suite, no linter configured.

## Architecture

Three modules; no framework, no async:

- **`tray.py`** — entry point and all core logic: config loading, SQLite DB, NBP API polling, alert detection, tray icon (Windows), headless polling loop.
- **`chart.py`** — standalone Tk/matplotlib window for rate history. Spawned as a **subprocess** by `tray.py` (`open_chart()`) so its Tk main loop doesn't block the pystray event loop. Can also run independently.
- **`notify.py`** — notification delivery only. `send_toast()` uses `windows_toasts`; `send_email()` uses `smtplib` SSL. Both swallow exceptions so delivery failures never crash the poll loop.

### Platform split

`requirements.txt` uses `sys_platform == "win32"` markers — `pystray`, `Pillow`, `windows-toasts`, and `matplotlib` are **not installed** on Linux (Docker). `tray.py` lazy-imports all four inside functions (`run_tray`, `make_icon_image`) so headless mode works without them.

### Data flow

1. `fetch_rate()` hits the NBP API and writes to `rates` table (SQLite, `rates.db`).
2. `check_alerts()` compares the new rate against the previous reading: spike by `spike_pct`%, or a threshold crossing. Threshold alerts fire once per crossing — they check `prev < threshold <= curr` (or vice versa), not just whether the current rate is past the bound.
3. `dispatch_alerts()` logs to the `alerts` table, optionally sends a toast, optionally sends email.

### Config

`config.json` is deep-merged over `DEFAULT_CONFIG` in `tray.py`. Missing file → defaults (email off, desktop notifications on). `USDPLN_DB_PATH` and `USDPLN_CONFIG_PATH` env vars override the default paths (used by Docker volumes).

### SQLite schema

```sql
CREATE TABLE rates  (ts INTEGER PRIMARY KEY, rate REAL NOT NULL);
CREATE TABLE alerts (ts INTEGER NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL);
```

`chart.py` queries `rates` with bucket aggregation: `(ts / bucket_seconds) * bucket_seconds` as the group key, then `AVG(rate)`.
