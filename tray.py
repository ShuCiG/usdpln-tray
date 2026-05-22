#!/usr/bin/env python3
"""USD/PLN tray app — tooltip shows current rate from NBP API."""

import threading
import time

import requests
from PIL import Image, ImageDraw, ImageFont
import pystray

REFRESH_INTERVAL = 300  # seconds


def fetch_rate() -> str:
    try:
        r = requests.get(
            "http://api.nbp.pl/api/exchangerates/rates/A/USD/?format=json",
            timeout=10,
        )
        r.raise_for_status()
        rate = r.json()["rates"][0]["mid"]
        return f"USD/PLN: {rate:.4f}"
    except Exception as e:
        return f"USD/PLN: błąd ({e})"


def make_icon_image(text: str) -> Image.Image:
    """Render rate text into a 64x64 icon."""
    img = Image.new("RGBA", (64, 64), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    # Try to use a small font; fall back to default
    try:
        import sys, os
        if sys.platform == "win32":
            font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arialbd.ttf")
        else:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 12)
    except Exception:
        font = ImageFont.load_default()
    draw.text((2, 24), "$", fill=(50, 200, 50, 255), font=font)
    return img


def run_tray():
    rate_label = fetch_rate()
    icon_image = make_icon_image(rate_label)

    icon = pystray.Icon(
        name="usdpln",
        icon=icon_image,
        title=rate_label,  # tooltip shown on hover
        menu=pystray.Menu(
            pystray.MenuItem(lambda text: text._icon.title, None, enabled=False),
            pystray.MenuItem("Odśwież", lambda icon, item: refresh(icon)),
            pystray.MenuItem("Wyjdź", lambda icon, item: icon.stop()),
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
