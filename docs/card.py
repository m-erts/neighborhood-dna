#!/usr/bin/env python3
"""Render docs/assets/card.svg to card.png, the 1200 x 630 image of link previews.

    python docs/card.py

LinkedIn and X ignore SVG in og:image, so the card is kept as a PNG. Needs Google
Chrome or Chromium; nothing else in the repository depends on this file.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

ASSETS = pathlib.Path(__file__).parent / "assets"
BROWSERS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "google-chrome", "chromium", "chromium-browser"]

browser = next((b for b in BROWSERS if shutil.which(b) or pathlib.Path(b).exists()), None)
if browser is None:
    sys.exit("no Chrome or Chromium found")
with tempfile.TemporaryDirectory() as scratch:
    page = pathlib.Path(scratch) / "card.html"
    page.write_text('<!doctype html><style>html,body{margin:0;background:#0B0F19}'
                    'img{display:block;width:1200px;height:630px}</style>'
                    f'<img src="{(ASSETS / "card.svg").as_uri()}">')
    shot = pathlib.Path(scratch) / "card.png"
    command = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--force-device-scale-factor=1", "--window-size=1200,630",
               f"--user-data-dir={scratch}/profile", f"--screenshot={shot}", page.as_uri()]
    try:  # headless Chrome sometimes keeps running after it has written the file
        subprocess.run(command, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        pass
    if not shot.exists():
        sys.exit("the browser wrote no screenshot")
    shutil.copy(shot, ASSETS / "card.png")
print("docs/assets/card.png")
