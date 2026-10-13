from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from app.sop_api import router as sop_router
from .browser import browser_manager
from .digistore_collector import collect as collect_digistore
from .storage import CATEGORIES, ALL_CATEGORIES, storage

load_dotenv()

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
ASSETS = DATA / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
CDP_URL = os.getenv("DIGIFLOW_CDP_URL", "http://127.0.0.1:9222")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

app = FastAPI(title="DigiFlow", version="0.5.0")
app.include_router(sop_router)

JOB_LOCK = threading.RLock()
JOBS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Dashboard / health
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse((BASE / "app" / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "service": "digiflow", "version": app.version}


@app.get("/api/status")
def status():
    with JOB_LOCK:
        jobs = list(JOBS.values())[-10:]
    return {
        "ok": True,
        "browser": browser_manager.status(),
        "storage": storage.counts(),
        "categories": CATEGORIES,
        "all_categories": ALL_CATEGORIES,
        "jobs": jobs,
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


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.get("/api/products")
def get_products(category: str | None = None):
    return {"ok": True, "products": storage.products(category)}


@app.get("/api/products/all")
def get_all_products():
    return {"ok": True, "products": storage.products(ALL_CATEGORIES)}


@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    product = storage.product(product_id)
    if not product:
        return JSONResponse({"ok": False, "error": "Product not found"}, status_code=404)
    return {"ok": True, "product": product}


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
        return {
            "ok": True,
            "product": storage.set_product_status(
                product_id,
                str(body.get("status", "")),
                body.get("approved") if "approved" in body else None,
            ),
        }
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------

def _number(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_finance(product_price, selling_price, commission_percent, other_cost, calculation_mode):
    product_price = _number(product_price)
    selling_price = _number(selling_price)
    commission_percent = _number(commission_percent)
    other_cost = _number(other_cost)
    mode = str(calculation_mode or "affiliate").strip().lower()
    if mode not in {"affiliate", "reseller"}:
        raise ValueError("calculation_mode must be affiliate or reseller")
    if mode == "affiliate":
        expected_earnings = product_price * commission_percent / 100
        gross_profit = expected_earnings
        margin_base = product_price
    else:
        gross_profit = selling_price - product_price
        expected_earnings = gross_profit
        margin_base = selling_price
    net_profit = gross_profit - other_cost
    return {
        "product_price": round(product_price, 2),
        "selling_price": round(selling_price, 2),
        "commission_percent": round(commission_percent, 2),
        "expected_earnings": round(expected_earnings, 2),
        "other_cost": round(other_cost, 2),
        "gross_profit": round(gross_profit, 2),
        "total_cost": round(other_cost, 2),
        "net_profit": round(net_profit, 2),
        "profit_margin": round((net_profit / margin_base) * 100 if margin_base > 0 else 0.0, 2),
        "calculation_mode": mode,
    }


@app.post("/api/finance/calculate")
def finance_calculate(body: dict):
    try:
        return {"ok": True, "calculation": calculate_finance(
            body.get("product_price"), body.get("selling_price"),
            body.get("commission_percent"), body.get("other_cost"), body.get("calculation_mode")
        )}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.put("/api/products/{product_id}/finance")
def update_product_finance(product_id: int, body: dict):
    try:
        existing = storage.product(product_id)
        if not existing:
            return JSONResponse({"ok": False, "error": "Product not found"}, status_code=404)
        result = calculate_finance(
            body.get("product_price", existing.get("product_price", 0)),
            body.get("selling_price", existing.get("selling_price", 0)),
            body.get("commission_percent", existing.get("commission_percent", 0)),
            body.get("other_cost", existing.get("other_cost", 0)),
            body.get("calculation_mode", existing.get("calculation_mode", "affiliate")),
        )
        return {"ok": True, "product": storage.update_product_finance(product_id, **result)}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/api/finance/products")
def finance_products(category: str | None = None):
    return {"ok": True, "products": storage.products(category)}


@app.get("/api/finance/summary")
def finance_summary():
    products = storage.products(ALL_CATEGORIES)
    product_value = expected_earnings = total_cost = net_profit = 0.0
    margins = []
    by_category = {}
    for product in products:
        price = _number(product.get("product_price"))
        earnings = _number(product.get("expected_earnings"))
        cost = _number(product.get("other_cost"))
        profit = _number(product.get("net_profit"))
        margin = _number(product.get("profit_margin"))
        product_value += price; expected_earnings += earnings; total_cost += cost; net_profit += profit
        if product.get("profit_margin") is not None:
            margins.append(margin)
        category = product.get("category") or "Uncategorized"
        bucket = by_category.setdefault(category, {"products": 0, "product_value": 0.0, "expected_earnings": 0.0, "total_cost": 0.0, "net_profit": 0.0})
        bucket["products"] += 1; bucket["product_value"] += price; bucket["expected_earnings"] += earnings; bucket["total_cost"] += cost; bucket["net_profit"] += profit
    for bucket in by_category.values():
        base = bucket["product_value"]
        bucket["margin"] = round(bucket["net_profit"] / base * 100 if base > 0 else 0.0, 2)
        for key in ("product_value", "expected_earnings", "total_cost", "net_profit"):
            bucket[key] = round(bucket[key], 2)
    return {"ok": True, "summary": {"total_products": len(products), "product_value": round(product_value, 2), "expected_earnings": round(expected_earnings, 2), "total_cost": round(total_cost, 2), "net_profit": round(net_profit, 2), "average_margin": round(sum(margins) / len(margins) if margins else 0.0, 2), "by_category": by_category}}


# ---------------------------------------------------------------------------
# Review center
# ---------------------------------------------------------------------------

@app.get("/api/review")
def review_queue():
    products = storage.products()
    return {"ok": True, "products": [p for p in products if p["status"] in {"collected", "verified", "rejected", "approved", "content_ready", "image_ready", "pin_ready"}]}


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


# ---------------------------------------------------------------------------
# Runs / tasks
# ---------------------------------------------------------------------------

@app.post("/api/runs")
def create_run(body: dict):
    try:
        target = int(body.get("target_count", 60) or 60)
        if not 1 <= target <= 60:
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
    return {"ok": True, "stages": {"content": [], "images": [], "pins": []}}


@app.get("/api/audit")
def audit():
    return {"ok": True, "events": storage.audit_rows()}


# ---------------------------------------------------------------------------
# Full pipeline orchestration
# ---------------------------------------------------------------------------

def _job_set(job_id: str, **patch):
    with JOB_LOCK:
        JOBS.setdefault(job_id, {"job_id": job_id})
        JOBS[job_id].update(patch)
        JOBS[job_id]["updated_at"] = time.time()


def _job_progress(job_id: str, message: str, progress: int | None = None, **extra):
    data = {"message": message}
    if progress is not None:
        data["progress"] = max(0, min(100, int(progress)))
    data.update(extra)
    _job_set(job_id, **data)


def _connect_cdp():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(CDP_URL)
    if not browser.contexts:
        pw.stop()
        raise RuntimeError("No Chrome context is available on CDP port 9222")
    context = browser.contexts[0]
    return pw, browser, context


def _page_for_host(context, host: str, url: str | None = None):
    page = next((p for p in context.pages if host in p.url), None)
    if page is None:
        page = context.new_page()
    if url and host not in page.url:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    return page


def _is_login_page(page) -> bool:
    text = ""
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        pass
    return any(x in text for x in ("sign in", "log in", "login")) and any(x in page.url.lower() for x in ("auth", "login", "signin"))


def _ollama_copy(product: dict) -> dict:
    details = product.get("details") or {}
    name = product.get("name") or details.get("name") or "Product"
    category = product.get("category") or details.get("internal_category") or ""
    description = details.get("description") or ""
    prompt = f"""Create original Pinterest marketing copy for this affiliate product.\n\nProduct: {name}\nCategory: {category}\nSource description: {description[:3500]}\n\nReturn JSON only with: title (max 100 chars), description (max 500 chars), keywords (5-10 short phrases). Be specific to the product. Do not invent features, statistics, testimonials, credentials, guarantees, income claims, or medical claims. Do not mention AI. Keep health/finance wording conservative."""
    fallback_title = str(name)[:100]
    fallback_description = clean_text(description)[:500] if description else f"Explore {name} and see whether it fits your goals and interests."[:500]
    fallback_keywords = [category.lower(), "product guide", "online learning", "resources"]
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=180)
        r.raise_for_status()
        raw = str(r.json().get("response", "")).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        data = json.loads(raw)
        title = " ".join(str(data.get("title", "")).split())[:100]
        desc = " ".join(str(data.get("description", "")).split())[:500]
        keywords = data.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [x.strip() for x in keywords.split(",")]
        keywords = [" ".join(str(x).split())[:60] for x in keywords if str(x).strip()][:10]
        if not title or not desc:
            raise ValueError("Ollama returned incomplete copy")
        return {"title": title, "description": desc, "keywords": keywords or fallback_keywords, "model": OLLAMA_MODEL}
    except Exception as exc:
        return {"title": fallback_title, "description": fallback_description, "keywords": fallback_keywords, "model": "fallback", "warning": str(exc)}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _find_first(page, selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _click_text(page, labels, timeout=8000):
    for label in labels:
        try:
            loc = page.get_by_text(label, exact=True).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def _adobe_export(product: dict, copy_data: dict, job_id: str) -> dict:
    """Best-effort Adobe Express Premium browser workflow.

    The workflow intentionally stops with a clear needs_user result if Adobe's
    current editor cannot be controlled by stable DOM controls. It never claims
    an export succeeded unless a real downloaded file exists.
    """
    product_id = product["id"]
    out_dir = ASSETS / str(product_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = out_dir / "pinterest.png"

    pw, browser, context = _connect_cdp()
    try:
        page = _page_for_host(context, "adobe.com", "https://www.adobe.com/express/create/ai/template-generator")
        if _is_login_page(page):
            return {"status": "needs_user", "reason": "Adobe Express login is required in the dedicated browser profile."}

        _job_progress(job_id, f"Adobe Express: opening template generator for {product['name']}")
        page.wait_for_timeout(1500)
        prompt = (
            "Pinterest vertical 2:3 promotional graphic for an affiliate product. "
            f"Product: {product['name']}. Category: {product['category']}. "
            "Clean premium editorial layout, strong readable headline, one short supporting line, "
            "no fake claims, no testimonials, no statistics, no guarantees."
        )
        box = _find_first(page, [
            'textarea[placeholder*="Describe"]',
            'textarea[placeholder*="prompt"]',
            'textarea',
            'input[placeholder*="Describe"]',
            'input[placeholder*="prompt"]',
        ])
        if not box:
            return {"status": "needs_user", "reason": "Adobe Express template prompt field was not found."}
        box.fill(prompt)
        if not _click_text(page, ["Generate", "Generate template"], timeout=10000):
            try:
                page.get_by_role("button", name=re.compile("Generate", re.I)).first.click(timeout=10000)
            except Exception:
                return {"status": "needs_user", "reason": "Adobe Express Generate control was not found."}

        page.wait_for_timeout(7000)
        if not _click_text(page, ["Edit template", "Customize template", "Customize"], timeout=10000):
            try:
                page.get_by_role("button", name=re.compile("Edit template|Customize", re.I)).first.click(timeout=10000)
            except Exception:
                return {"status": "needs_user", "reason": "Adobe Express generated a result but the template edit control was not found."}

        page.wait_for_timeout(5000)
        download_button = None
        for label in ["Download", "Download design"]:
            try:
                download_button = page.get_by_role("button", name=re.compile(label, re.I)).first
                if download_button.count() and download_button.is_visible():
                    break
            except Exception:
                download_button = None
        if not download_button:
            return {"status": "needs_user", "reason": "Adobe Express Download control was not found."}

        try:
            with page.expect_download(timeout=30000) as dl_info:
                download_button.click()
            download = dl_info.value
            download.save_as(str(expected))
        except Exception as exc:
            return {"status": "needs_user", "reason": f"Adobe Express did not produce a downloadable asset: {exc}"}

        if not expected.exists() or expected.stat().st_size < 1000:
            return {"status": "needs_user", "reason": "Downloaded Adobe asset is missing or empty."}

        storage.upsert_asset(product_id, "image", str(expected), "created")
        storage.update_product_details(product_id, {"adobe": {"status": "completed", "asset_path": str(expected), "template_mode": "ai_template_generator", "completed_at": time.time()}})
        storage.set_product_status(product_id, "image_ready")
        return {"status": "completed", "path": str(expected)}
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def _prepare_pinterest(product: dict, copy_data: dict, image_path: str, job_id: str) -> dict:
    pw, browser, context = _connect_cdp()
    try:
        page = _page_for_host(context, "pinterest.com", "https://www.pinterest.com/pin-creation-tool/")
        if _is_login_page(page):
            return {"status": "needs_user", "reason": "Pinterest login is required in the dedicated browser profile."}
        _job_progress(job_id, f"Pinterest: preparing Pin for {product['name']}")
        page.wait_for_timeout(2500)

        file_input = _find_first(page, ['input[type="file"]'])
        if not file_input:
            _click_text(page, ["Create Pin", "Create"], timeout=8000)
            page.wait_for_timeout(1500)
            file_input = _find_first(page, ['input[type="file"]'])
        if not file_input:
            return {"status": "needs_user", "reason": "Pinterest image upload control was not found."}
        file_input.set_input_files(image_path)
        page.wait_for_timeout(1800)

        title = copy_data["title"]
        description = copy_data["description"]
        destination = (product.get("details") or {}).get("promotion_url") or product["url"]

        title_box = _find_first(page, [
            'input[placeholder*="Title"]', 'input[aria-label*="Title"]', 'textarea[placeholder*="Title"]'
        ])
        if title_box:
            title_box.fill(title)

        desc_box = _find_first(page, [
            'textarea[placeholder*="Description"]', 'textarea[aria-label*="Description"]'
        ])
        if desc_box:
            desc_box.fill(description)

        url_box = _find_first(page, [
            'input[placeholder*="link"]', 'input[placeholder*="URL"]', 'input[aria-label*="link"]', 'input[aria-label*="URL"]'
        ])
        if url_box:
            url_box.fill(destination)

        storage.upsert_pin(product["id"], title, description, destination, "ready_for_review")
        storage.update_product_details(product["id"], {"pinterest": {"status": "ready_for_review", "keywords": copy_data.get("keywords", []), "destination_url": destination, "prepared_at": time.time()}})
        storage.set_product_status(product["id"], "pin_ready")
        return {"status": "ready_for_review", "url": destination}
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def _run_approved_pipeline(job_id: str):
    products = storage.approved_products()
    if not products:
        _job_set(job_id, status="blocked", message="No approved products. Approve products in Review Center first.")
        return
    total = len(products)
    _job_set(job_id, status="running", stage="content", total=total, completed=0)
    for index, product in enumerate(products, 1):
        try:
            _job_progress(job_id, f"{index}/{total}: generating local Ollama copy", int((index - 1) / total * 100), current_product=product["name"], stage="content")
            copy_data = _ollama_copy(product)
            storage.upsert_content(product["id"], copy_data["title"], copy_data["description"], copy_data["keywords"])
            storage.update_product_details(product["id"], {"content": copy_data})
            storage.set_product_status(product["id"], "content_ready")

            _job_progress(job_id, f"{index}/{total}: creating Adobe Express asset", int((index - 0.45) / total * 100), current_product=product["name"], stage="images")
            adobe = _adobe_export(product, copy_data, job_id)
            if adobe.get("status") != "completed":
                storage.update_product_details(product["id"], {"adobe": adobe})
                _job_set(job_id, last_error=adobe.get("reason"), current_product=product["name"], stage="images")
                continue

            _job_progress(job_id, f"{index}/{total}: preparing Pinterest Pin", int((index - 0.15) / total * 100), current_product=product["name"], stage="pinterest")
            pin = _prepare_pinterest(product, copy_data, adobe["path"], job_id)
            if pin.get("status") != "ready_for_review":
                storage.update_product_details(product["id"], {"pinterest": pin})
                _job_set(job_id, last_error=pin.get("reason"), current_product=product["name"], stage="pinterest")
        except Exception as exc:
            storage.update_product_details(product["id"], {"pipeline_error": str(exc), "pipeline_error_at": time.time()})
            try:
                storage.set_product_status(product["id"], "error")
            except Exception:
                pass
            _job_set(job_id, last_error=str(exc), current_product=product["name"])
        finally:
            _job_set(job_id, completed=index)

    _job_progress(job_id, "Approved-product pipeline finished. Pinterest Pins are prepared; Publish remains manual.", 100, stage="complete")
    _job_set(job_id, status="completed")


def _run_collection(job_id: str, target: int, max_pages: int):
    run = storage.create_run("product_collection", None, target)
    task = storage.create_task("product_collection", {"run_id": run["id"], "target_count": target})
    storage.update_run(run["id"], "running", "Collecting Digistore24 products")
    storage.update_task(task["id"], "running", 0)
    _job_set(job_id, status="running", stage="collection", run_id=run["id"], task_id=task["id"], target=target, collected=0)

    def progress(evt):
        typ = evt.get("type")
        if typ in {"product_accepted", "product_accepted_fallback"}:
            collected = int(evt.get("collected", 0))
            pct = int(collected / target * 100) if target else 0
            storage.update_task(task["id"], "running", pct)
            _job_progress(job_id, f"Collected {collected}/{target}: {evt.get('product')}", pct, category=evt.get("category"), collected=collected)
        elif typ == "marketplace_page":
            _job_progress(job_id, f"Scanning Digistore24 marketplace page {evt.get('page')}", None, page=evt.get("page"))

    try:
        result = collect_digistore(target=target, api_base="http://127.0.0.1:8787", max_pages=max_pages, pause=0.25, dry_run=False, on_progress=progress)
        storage.update_run(run["id"], "awaiting_review", f"Collection complete: {result.get('collected', 0)} products. Review required.")
        storage.update_task(task["id"], "completed", 100, payload_patch={"result": result})
        _job_progress(job_id, f"Collection complete: {result.get('collected', 0)}/{target}. Waiting for Review Center approval.", 100, stage="review", result=result)
        _job_set(job_id, status="awaiting_review")
    except Exception as exc:
        storage.update_run(run["id"], "error", str(exc))
        storage.update_task(task["id"], "failed", 0, str(exc))
        _job_set(job_id, status="failed", last_error=str(exc), stage="collection")


@app.post("/api/pipeline/collect")
def start_collection(body: dict):
    target = int(body.get("target_count", 60) or 60)
    max_pages = int(body.get("max_pages", 124) or 124)
    if not 1 <= target <= 60:
        return JSONResponse({"ok": False, "error": "target_count must be between 1 and 60"}, status_code=400)
    with JOB_LOCK:
        if any(j.get("status") == "running" for j in JOBS.values()):
            return JSONResponse({"ok": False, "error": "A DigiFlow job is already running."}, status_code=409)
        job_id = f"collection-{int(time.time())}"
        JOBS[job_id] = {"job_id": job_id, "status": "queued", "stage": "collection", "created_at": time.time()}
    threading.Thread(target=_run_collection, args=(job_id, target, max_pages), daemon=True, name="DigiFlowCollection").start()
    return {"ok": True, "job_id": job_id}


@app.post("/api/pipeline/approved")
def start_approved_pipeline():
    with JOB_LOCK:
        if any(j.get("status") == "running" for j in JOBS.values()):
            return JSONResponse({"ok": False, "error": "A DigiFlow job is already running."}, status_code=409)
        job_id = f"approved-{int(time.time())}"
        JOBS[job_id] = {"job_id": job_id, "status": "queued", "stage": "content", "created_at": time.time()}
    threading.Thread(target=_run_approved_pipeline, args=(job_id,), daemon=True, name="DigiFlowApprovedPipeline").start()
    return {"ok": True, "job_id": job_id, "approved_products": len(storage.approved_products())}


@app.get("/api/pipeline/jobs")
def pipeline_jobs():
    with JOB_LOCK:
        return {"ok": True, "jobs": list(JOBS.values())[-20:]}


app.mount("/static", StaticFiles(directory=BASE / "app" / "static"), name="static")
