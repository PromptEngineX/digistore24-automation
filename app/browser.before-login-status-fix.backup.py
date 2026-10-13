import os
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue

from playwright.sync_api import sync_playwright


BASE = Path(__file__).resolve().parents[1]

# Dedicated REAL Google Chrome profile.
# You will log into Google, Digistore24, Adobe Express and Pinterest
# manually in this profile.
CHROME_PROFILE = BASE / "profiles" / "chrome_automation"

CHROME_EXE = Path(
    os.getenv(
        "CHROME_EXE",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
)

CDP_HOST = "127.0.0.1"
CDP_PORT = int(os.getenv("CHROME_CDP_PORT", "9222"))

SITES = {
    "digistore": os.getenv(
        "DIGISTORE_URL",
        "https://www.digistore24.com/",
    ),
    "adobe": os.getenv(
        "ADOBE_URL",
        "https://new.express.adobe.com/",
    ),
    "pinterest": os.getenv(
        "PINTEREST_URL",
        "https://www.pinterest.com/",
    ),
}


class BrowserManager:
    def __init__(self):
        self._thread = None
        self._queue = Queue()
        self._ready = threading.Event()

        self._pw = None
        self._browser = None
        self._context = None
        self._pages = {}

        self._chrome_process = None

        self.browser_running = False
        self.last_error = None

    def _start(self):
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
            name="digiflow-browser",
        )
        self._thread.start()

        if not self._ready.wait(timeout=20):
            raise RuntimeError("Browser worker did not start.")

    def _worker(self):
        self._pw = sync_playwright().start()
        self._ready.set()

        while True:
            command = self._queue.get()

            if command is None:
                break

            action, payload, result = command

            try:
                if action == "open":
                    result["value"] = self._open_site(payload)

                elif action == "close":
                    result["value"] = self._close()

                elif action == "status":
                    result["value"] = self._status()

                elif action == "login_status":
                    result["value"] = self._login_status(payload)

            except Exception as exc:
                self.last_error = str(exc)
                result["error"] = exc

            finally:
                result["event"].set()

        self._shutdown()

    def _launch_real_chrome(self):
        CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

        if not CHROME_EXE.exists():
            raise FileNotFoundError(
                f"Google Chrome was not found at: {CHROME_EXE}"
            )

        # Launch actual installed Google Chrome, not Playwright Chromium.
        self._chrome_process = subprocess.Popen(
            [
                str(CHROME_EXE),
                f"--user-data-dir={CHROME_PROFILE}",
                "--profile-directory=Default",
                f"--remote-debugging-address={CDP_HOST}",
                f"--remote-debugging-port={CDP_PORT}",
                "--start-maximized",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Give Chrome time to initialize the debugging endpoint.
        deadline = time.time() + 15

        last_error = None

        while time.time() < deadline:
            try:
                self._browser = self._pw.chromium.connect_over_cdp(
                    f"http://{CDP_HOST}:{CDP_PORT}"
                )

                contexts = self._browser.contexts

                if not contexts:
                    raise RuntimeError(
                        "Chrome started, but no browser context is available."
                    )

                self._context = contexts[0]

                self.browser_running = True

                return

            except Exception as exc:
                last_error = exc
                time.sleep(0.5)

        raise RuntimeError(
            "Could not connect to the real Chrome CDP endpoint. "
            f"Last error: {last_error}"
        )

    def _ensure_chrome(self):
        # Reuse an already-running Chrome instance first.
        if self._browser and self._context:
            try:
                if not self._context.is_closed():
                    self.browser_running = True
                    return
            except Exception:
                pass

        # Reconnect to Chrome started by another Python process.
        try:
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://{CDP_HOST}:{CDP_PORT}"
            )

            contexts = self._browser.contexts

            if not contexts:
                raise RuntimeError(
                    "Chrome is reachable, but no browser context is available."
                )

            self._context = contexts[0]
            self.browser_running = True
            return

        except Exception:
            # No existing Chrome connection. Launch our dedicated instance.
            self._browser = None
            self._context = None
            self._launch_real_chrome()
    def _open_site(self, site):
        if site not in SITES:
            raise ValueError(
                f"Unknown site '{site}'. "
                f"Valid sites: {', '.join(SITES)}"
            )

        self._ensure_chrome()

        page = self._pages.get(site)

        if page and not page.is_closed():
            page.bring_to_front()

            return {
                "site": site,
                "url": page.url,
                "reused": True,
            }

        # Look for an existing tab already opened to this site.
        for existing_page in self._context.pages:
            if existing_page.is_closed():
                continue

            if SITES[site].split("/")[2] in existing_page.url:
                self._pages[site] = existing_page
                existing_page.bring_to_front()

                return {
                    "site": site,
                    "url": existing_page.url,
                    "reused": True,
                }

        page = self._context.new_page()

        self._pages[site] = page

        page.goto(
            SITES[site],
            wait_until="domcontentloaded",
        )

        return {
            "site": site,
            "url": page.url,
            "reused": False,
        }

    def _login_status(self, site):
        if site not in SITES:
            raise ValueError(f"Unknown site '{site}'.")

        # Reconnect to an already-running Chrome process if this is
        # a fresh Python process.
        self._ensure_chrome()

        target_host = SITES[site].split("/")[2].lower()

        page = self._pages.get(site)

        # Reuse the page already tracked by this manager.
        if not page or page.is_closed():
            page = None

        # If this manager is new, locate the existing site tab.
        if page is None:
            for existing_page in self._context.pages:
                if existing_page.is_closed():
                    continue

                if target_host in existing_page.url.lower():
                    page = existing_page
                    self._pages[site] = existing_page
                    break

        if page is None:
            return {
                "site": site,
                "browser_open": True,
                "logged_in": False,
                "url": None,
            }

        url = page.url.lower()

        login_words = (
            "login",
            "signin",
            "sign-in",
            "authenticate",
        )

        logged_in = not any(
            word in url
            for word in login_words
        )

        return {
            "site": site,
            "browser_open": True,
            "logged_in": logged_in,
            "url": page.url,
        }
    def _close(self):
        self._pages.clear()
        self._context = None
        self._browser = None
        self.browser_running = False

        # We intentionally do not delete the Chrome profile.
        # Authentication/session data remains on disk.

        return True

    def _shutdown(self):
        self._close()

        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

        self._pw = None

    def _call(self, action, payload=None):
        self._start()

        result = {
            "event": threading.Event(),
        }

        self._queue.put(
            (
                action,
                payload,
                result,
            )
        )

        if not result["event"].wait(timeout=30):
            raise TimeoutError(
                f"Browser command '{action}' timed out."
            )

        if "error" in result:
            raise result["error"]

        return result.get("value")

    def open_site(self, site):
        return self._call("open", site)

    def login_status(self, site):
        return self._call("login_status", site)

    def close(self):
        try:
            return self._call("close")
        except Exception:
            return False

    def status(self):
        try:
            return self._call("status")
        except Exception as exc:
            return {
                "running": False,
                "profile": str(CHROME_PROFILE),
                "error": str(exc),
            }

    def _status(self):
        pages = []

        if self._context:
            for page in self._context.pages:
                if not page.is_closed():
                    pages.append(page.url)

        return {
            "running": self.browser_running,
            "chrome": str(CHROME_EXE),
            "profile": str(CHROME_PROFILE),
            "cdp": f"http://{CDP_HOST}:{CDP_PORT}",
            "pages": pages,
            "last_error": self.last_error,
        }


browser_manager = BrowserManager()