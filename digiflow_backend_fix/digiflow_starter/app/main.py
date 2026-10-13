from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .browser import browser_manager
from .storage import CATEGORIES, ALL_CATEGORIES, storage

load_dotenv()

BASE = Path(__file__).resolve().parents[1]
app = FastAPI(title="DigiFlow", version="0.2.0")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((BASE / "app" / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "service": "digiflow", "version": app.version}


@app.get("/api/status")
def status():
    return {
        "ok": True,
        "browser": browser_manager.status(),
        "storage": storage.counts(),
        "categories": CATEGORIES,
        "all_categories": ALL_CATEGORIES,
    }


@app.post("/api/open/{site}")
def open_site(site: str):
    try:
        browser_manager.open_site(site)
        return {"ok": True, "site": site, "browser": browser_manager.status()}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/close")
def close_browser():
    browser_manager.close()
    return {"ok": True, "browser": browser_manager.status()}


@app.get("/api/products")
def get_products(category: str | None = None):
    return {"ok": True, "products": storage.products(category)}


@app.post("/api/products")
def add_product(body: dict):
    try:
        product = storage.add_product(
            category=str(body.get("category", "")),
            name=str(body.get("name", "")),
            url=str(body.get("url", "")),
            amount=str(body.get("amount", "")),
            currency=str(body.get("currency", "")).strip() or None,
            details=body.get("details") if isinstance(body.get("details"), dict) else {},
        )
        return {"ok": True, "product": product}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/products/{product_id}/status")
def product_status(product_id: int, body: dict):
    try:
        product = storage.set_product_status(
            product_id,
            str(body.get("status", "")),
            body.get("approved") if "approved" in body else None,
        )
        return {"ok": True, "product": product}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/api/review")
def review_queue():
    products = storage.products()
    return {"ok": True, "products": [p for p in products if p["status"] in {"collected", "verified", "rejected", "approved"}]}


@app.post("/api/review/{product_id}/approve")
def approve_product(product_id: int):
    try:
        return {"ok": True, "product": storage.set_product_status(product_id, "approved", True)}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)


@app.post("/api/review/{product_id}/reject")
def reject_product(product_id: int):
    try:
        return {"ok": True, "product": storage.set_product_status(product_id, "rejected", False)}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)


@app.post("/api/runs")
def create_run(body: dict):
    try:
        target = int(body.get("target_count", 60) or 60)
        if target < 1 or target > 60:
            raise ValueError("target_count must be between 1 and 60")
        category = str(body.get("category", "")).strip() or None
        if category and category != ALL_CATEGORIES and category not in CATEGORIES:
            raise ValueError("Invalid category")
        run = storage.create_run(str(body.get("kind", "product_collection")), category, target)
        task = storage.create_task("product_collection", {"run_id": run["id"], "category": category, "target_count": target})
        return {"ok": True, "run": run, "task": task}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.get("/api/runs")
def get_runs():
    return {"ok": True, "runs": storage.runs()}


@app.get("/api/tasks")
def get_tasks():
    return {"ok": True, "tasks": storage.tasks()}


@app.post("/api/tasks")
def create_task(body: dict):
    kind = str(body.get("kind", "manual")).strip() or "manual"
    return {"ok": True, "task": storage.create_task(kind, body.get("payload") if isinstance(body.get("payload"), dict) else {})}


@app.get("/api/stages")
def stages():
    # Stage data is intentionally read-only here; later adapters populate these tables.
    return {"ok": True, "stages": {"content": [], "images": [], "pins": []}}

@app.get("/api/audit")
def audit():
    return {"ok": True, "events": storage.audit_rows()}


app.mount("/static", StaticFiles(directory=BASE / "app" / "static"), name="static")
