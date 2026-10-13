# DigiFlow — Digistore24 / Adobe Express / Pinterest starter

This starter keeps all browser profile data and application data under the project folder.
First login is manual. Playwright uses a persistent Chromium profile, so subsequent runs reuse the same cookies/session where the sites allow it.

## Setup on Windows

1. Put this folder at `E:\automation-hub\digiflow`.
2. Open PowerShell in that folder.
3. Create a virtual environment:
   `py -m venv .venv`
4. Activate:
   `.\.venv\Scripts\Activate.ps1`
5. Install:
   `python -m pip install -r requirements.txt`
6. Install Chromium for Playwright:
   `python -m playwright install chromium`
7. Copy `.env.example` to `.env`.
8. Start:
   `python run.py`
9. Open the local dashboard shown in the terminal.

Use the dashboard buttons to open/login to each service. The first login is manual. Do not put passwords into source code.

## Important

- The browser profile is local to this project under `profiles\chromium`.
- Keep this folder private because it contains browser session data.
- This starter does not auto-publish anything.
- Pinterest final publishing remains a human approval step.
