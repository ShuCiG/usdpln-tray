# usdpln-tray

Shows the USD/PLN exchange rate in the system tray. Data from the NBP API (National Bank of Poland).

## Install and run (Windows)

```bat
pip install -r requirements.txt
python tray.py
```

The rate refreshes every hour and each sample is logged to `rates.db` (SQLite, created next to `tray.py`). Right-click the icon for the menu (Refresh / Exit).
