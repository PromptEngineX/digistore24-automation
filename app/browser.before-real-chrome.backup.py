import os
import threading
from pathlib import Path
from queue import Queue, Empty

from playwright.sync_api import sync_playwright


BASE = Path(__file__).resolve().parents[1]

PROFILES = {
    "digistore": BASE / "profiles" / "digistore24",
    "adobe": BASE / "profiles" / "adobe_express",
    "pinterest": BASE / "profiles" / "pinterest",
}

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
        self._contexts = {}
        self._pages = {}

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
            try:
                command = self._queue.get()
            except Exception:
                continue

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

        self._shutdown_playwright()

    def _launch_profile(self, site):
        profile = PROFILES[site]
        profile.mkdir(parents=True, exist_ok=True)

        context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            viewport={
                "width": 1440,
                "height": 900,
            },
            args=[
                "--start-maximized",
            ],
        )

        self._contexts[site] = context

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        self._pages[site] = page

        self.browser_running = True

        return page

    def _open_site(self, site):
        if site not in SITES:
            raise ValueError(
                f"Unknown site '{site}'. "
                f"Valid sites: {', '.join(SITES)}"
            )

        page = self._pages.get(site)
        context = self._contexts.get(site)

        # Reuse an already-open profile/page.
        if context and not context.is_closed():
            if page and not page.is_closed():
                page.bring_to_front()
                return {
                    "site": site,
                    "url": page.url,
                    "reused": True,
                }

        # Launch the site's persistent profile.
        page = self._launch_profile(site)

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

        page = self._pages.get(site)

        if not page or page.is_closed():
            return {
                "site": site,
                "browser_open": False,
                "logged_in": False,
                "url": None,
            }

        url = page.url.lower()

        # This is deliberately conservative.
        # We don't submit login forms or attempt to bypass
        # site authentication protections.
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
        for context in list(self._contexts.values()):
            try:
                if not context.is_closed():
                    context.close()
            except Exception:
                pass

        self._contexts.clear()
        self._pages.clear()
        self.browser_running = False

        return True

    def _shutdown_playwright(self):
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
                "profiles": {},
                "error": str(exc),
            }

    def _status(self):
        profiles = {}

        for site in SITES:
            context = self._contexts.get(site)
            page = self._pages.get(site)

            profiles[site] = {
                "profile": str(PROFILES[site]),
                "open": bool(
                    context
                    and not context.is_closed()
                ),
                "page_open": bool(
                    page
                    and not page.is_closed()
                ),
                "url": (
                    page.url
                    if page and not page.is_closed()
                    else None
                ),
            }

        return {
            "running": self.browser_running,
            "profiles": profiles,
            "last_error": self.last_error,
        }


browser_manager = BrowserManager()