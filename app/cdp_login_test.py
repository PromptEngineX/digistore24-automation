from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(r"E:\digiflow_starter\profiles\digistore24")
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    print("Starting DigiFlow Chrome...")

    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1440, "height": 900},
        args=[
            "--remote-debugging-port=9222",
            "--start-maximized",
        ],
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://www.digistore24.com/", wait_until="domcontentloaded")

    print()
    print("====================================")
    print(" DIGIFLOW BROWSER IS READY")
    print("====================================")
    print()
    print("Log into Digistore24 MANUALLY.")
    print("Complete 2FA if Digistore24 asks for it.")
    print("Leave this browser open.")
    print()
    input("Press ENTER only after you are logged in...")

    print("Browser remains open for CDP test.")
    input("Press ENTER to close browser...")

    context.close()
