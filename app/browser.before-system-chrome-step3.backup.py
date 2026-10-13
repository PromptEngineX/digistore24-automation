import os
import threading
import queue
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parents[1]
PROFILE = BASE / "profiles" / "chromium"
PROFILE.mkdir(parents=True, exist_ok=True)

SITES = {
    "digistore": os.getenv(
        "DIGISTORE_URL",
        "https://www.digistore24.com/"
    ),
    "adobe": os.getenv(
        "ADOBE_URL",
        "https://new.express.adobe.com/"
    ),
    "pinterest": os.getenv(
        "PINTEREST_URL",
        "https://www.pinterest.com/"
    ),
}


class BrowserManager:
    def __init__(self):
        self.thread = None
        self.commands = queue.Queue()
        self.ready = threading.Event()
        self.stopped = threading.Event()

        self.browser_running = False
        self.pages = {}
        self.last_error = None

    def _launch_context(self, pw):
        return pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 1440, "height": 900},
            args=[
                "--start-maximized",
            ],
        )

    def _browser_worker(self):
        pw = None
        context = None

        try:
            pw = sync_playwright().start()

            context = self._launch_context(pw)

            self.browser_running = True
            self.last_error = None
            self.ready.set()

            while not self.stopped.is_set():
                try:
                    command = self.commands.get(timeout=0.25)
                except queue.Empty:
                    continue

                action = command.get("action")
                site = command.get("site")
                result = command.get("result")

                try:
                    if action == "open":
                        if site not in SITES:
                            raise ValueError(f"Unknown site: {site}")

                        page = self.pages.get(site)

                        if page and not page.is_closed():
                            page.bring_to_front()
                        else:
                            try:
                                page = context.new_page()
                            except Exception:
                                try:
                                    context.close()
                                except Exception:
                                    pass

                                self.pages = {}
                                context = self._launch_context(pw)
                                self.browser_running = True

                                page = context.new_page()

                            self.pages[site] = page

                            page.goto(
                                SITES[site],
                                wait_until="domcontentloaded",
                                timeout=60000,
                            )

                        result["ok"] = True
                        result["site"] = site

                    elif action == "status":
                        result["ok"] = True
                        result["browser"] = self.browser_running
                        result["sites"] = {
                            name: bool(
                                page and not page.is_closed()
                            )
                            for name, page in self.pages.items()
                        }

                    elif action == "close":
                        result["ok"] = True
                        self.stopped.set()

                except Exception as exc:
                    self.last_error = str(exc)
                    result["ok"] = False
                    result["error"] = str(exc)

                finally:
                    if "event" in command:
                        command["event"].set()

        except Exception as exc:
            self.last_error = str(exc)
            self.browser_running = False
            self.ready.set()

        finally:
            self.browser_running = False

            try:
                if context:
                    context.close()
            except Exception:
                pass

            try:
                if pw:
                    pw.stop()
            except Exception:
                pass

    def ensure(self):
        if self.thread and self.thread.is_alive():
            return

        self.stopped.clear()
        self.ready.clear()

        self.thread = threading.Thread(
            target=self._browser_worker,
            name="DigiFlow-Browser",
            daemon=True,
        )

        self.thread.start()

        self.ready.wait(timeout=30)

        if not self.browser_running:
            error = self.last_error or "Browser failed to start."
            raise RuntimeError(error)

    def _send(self, action, site=None, timeout=90):
        self.ensure()

        result = {}
        event = threading.Event()

        self.commands.put({
            "action": action,
            "site": site,
            "result": result,
            "event": event,
        })

        if not event.wait(timeout):
            raise TimeoutError(
                f"Browser command timed out: {action}"
            )

        if not result.get("ok"):
            raise RuntimeError(
                result.get("error", "Unknown browser error")
            )

        return result

    def open_site(self, site):
        return self._send("open", site=site)

    def status(self):
        try:
            if not self.thread or not self.thread.is_alive():
                return {
                    "browser": False,
                    "sites": {},
                    "error": self.last_error,
                }

            return self._send("status", timeout=10)

        except Exception as exc:
            return {
                "browser": self.browser_running,
                "sites": {},
                "error": str(exc),
            }

    def close(self):
        if not self.thread or not self.thread.is_alive():
            return

        try:
            self._send("close", timeout=10)
        except Exception:
            pass

        self.stopped.set()

        if self.thread:
            self.thread.join(timeout=10)

        self.thread = None
        self.browser_running = False


browser_manager = BrowserManager()
