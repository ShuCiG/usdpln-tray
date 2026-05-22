#!/usr/bin/env python3
"""USD/PLN tray app — tooltip shows current rate from NBP API."""

import os
import sqlite3
import threading
import time

import requests
from PIL import Image, ImageDraw, ImageFont
import pystray

REFRESH_INTERVAL = 3600  # seconds (1 hour)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rates.db")


def init_db() -> None:
    """Create the rates table if missing."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS rates ("
            "ts INTEGER PRIMARY KEY, rate REAL NOT NULL)"
        )


def save_rate(rate: float) -> None:
    """Store one rate sample keyed by unix timestamp."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rates (ts, rate) VALUES (?, ?)",
            (int(time.time()), rate),
        )


def fetch_rate() -> str:
    try:
        r = requests.get(
            "http://api.nbp.pl/api/exchangerates/rates/A/USD/?format=json",
            timeout=10,
        )
        r.raise_for_status()
        rate = r.json()["rates"][0]["mid"]
        try:
            save_rate(rate)
        except Exception:
            pass  # DB write failure must not break the tray
        return f"USD/PLN: {rate:.4f}"
    except Exception as e:
        return f"USD/PLN: error ({e})"


def make_icon_image(text: str) -> Image.Image:
    """Render a large centered '$' into a 64x64 icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    # Try to use a bold font sized to fill the icon; fall back to default
    try:
        import sys
        if sys.platform == "win32":
            font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf")
        else:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 52)
    except Exception:
        font = ImageFont.load_default()
    glyph = "$"
    # Center the glyph using its real bounding box
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
    x = (size - (right - left)) / 2 - left
    y = (size - (bottom - top)) / 2 - top
    draw.text((x, y), glyph, fill=(50, 200, 50, 255), font=font)
    return img


def run_tray():
    init_db()
    rate_label = fetch_rate()
    icon_image = make_icon_image(rate_label)

    icon = pystray.Icon(
        name="usdpln",
        icon=icon_image,
        title=rate_label,  # tooltip shown on hover
        menu=pystray.Menu(
            pystray.MenuItem(lambda item: icon.title, None, enabled=False),
            pystray.MenuItem("Refresh", lambda icon, item: refresh(icon)),
            pystray.MenuItem("Exit", lambda icon, item: icon.stop()),
        ),
    )

    def refresh(icon):
        label = fetch_rate()
        icon.title = label
        icon.icon = make_icon_image(label)

    def auto_refresh():
        while True:
            time.sleep(REFRESH_INTERVAL)
            if not icon.visible:
                break
            refresh(icon)

    t = threading.Thread(target=auto_refresh, daemon=True)
    t.start()

    icon.run()


if __name__ == "__main__":
    run_tray()
