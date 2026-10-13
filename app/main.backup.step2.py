from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .browser import browser_manager
from .storage import CATEGORIES, ALL_CATEGORIES, storage

load_dotenv()

BASE = Path(__file__).resolve().parents[1]
app = FastAPI(title="DigiFlow", version="0.3.0")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(
        (BASE / "app" / "dashboard.html").read_text(encoding="utf-8")
    )


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


# -----------------------------
# Products
# -----------------------------

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
        return JSONResponse(
            {"ok": False, "error": "Product not found"},
            status_code=404,
        )
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
            details=body.get("details")
            if isinstance(body.get("details"), dict)
            else {},
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


# -----------------------------
# Finance
# -----------------------------

def _number(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_finance(
    product_price,
    selling_price,
    commission_percent,
    other_cost,
    calculation_mode,
):
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
        total_cost = other_cost
        net_profit = gross_profit - total_cost
        margin_base = product_price
    else:
        gross_profit = selling_price - product_price
        expected_earnings = gross_profit
        total_cost = other_cost
        net_profit = gross_profit - total_cost
        margin_base = selling_price

    profit_margin = (
        (net_profit / margin_base) * 100
        if margin_base > 0
        else 0.0
    )

    return {
        "product_price": round(product_price, 2),
        "selling_price": round(selling_price, 2),
        "commission_percent": round(commission_percent, 2),
        "expected_earnings": round(expected_earnings, 2),
        "other_cost": round(other_cost, 2),
        "gross_profit": round(gross_profit, 2),
        "total_cost": round(total_cost, 2),
        "net_profit": round(net_profit, 2),
        "profit_margin": round(profit_margin, 2),
        "calculation_mode": mode,
    }


@app.post("/api/finance/calculate")
def finance_calculate(body: dict):
    try:
        result = calculate_finance(
            product_price=body.get("product_price"),
            selling_price=body.get("selling_price"),
            commission_percent=body.get("commission_percent"),
            other_cost=body.get("other_cost"),
            calculation_mode=body.get("calculation_mode"),
        )
        return {"ok": True, "calculation": result}
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.put("/api/products/{product_id}/finance")
def update_product_finance(product_id: int, body: dict):
    try:
        existing = storage.product(product_id)
        if not existing:
            return JSONResponse(
                {"ok": False, "error": "Product not found"},
                status_code=404,
            )

        result = calculate_finance(
            product_price=body.get(
                "product_price",
                existing.get("product_price", 0),
            ),
            selling_price=body.get(
                "selling_price",
                existing.get("selling_price", 0),
            ),
            commission_percent=body.get(
                "commission_percent",
                existing.get("commission_percent", 0),
            ),
            other_cost=body.get(
                "other_cost",
                existing.get("other_cost", 0),
            ),
            calculation_mode=body.get(
                "calculation_mode",
                existing.get("calculation_mode", "affiliate"),
            ),
        )

        product = storage.update_product_finance(
            product_id,
            **result,
        )

        return {"ok": True, "product": product}
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

    product_value = 0.0
    expected_earnings = 0.0
    total_cost = 0.0
    net_profit = 0.0
    margins = []

    by_category = {}

    for product in products:
        price = _number(product.get("product_price"))
        earnings = _number(product.get("expected_earnings"))
        cost = _number(product.get("other_cost"))
        profit = _number(product.get("net_profit"))
        margin = _number(product.get("profit_margin"))

        product_value += price
        expected_earnings += earnings
        total_cost += cost
        net_profit += profit

        if product.get("profit_margin") is not None:
            margins.append(margin)

        category = product.get("category") or "Uncategorized"
        bucket = by_category.setdefault(
            category,
            {
                "products": 0,
                "product_value": 0.0,
                "expected_earnings": 0.0,
                "total_cost": 0.0,
                "net_profit": 0.0,
            },
        )
        bucket["products"] += 1
        bucket["product_value"] += price
        bucket["expected_earnings"] += earnings
        bucket["total_cost"] += cost
        bucket["net_profit"] += profit

    for bucket in by_category.values():
        base = bucket["product_value"]
        bucket["margin"] = round(
            (bucket["net_profit"] / base) * 100 if base > 0 else 0.0,
            2,
        )
        for key in (
            "product_value",
            "expected_earnings",
            "total_cost",
            "net_profit",
        ):
            bucket[key] = round(bucket[key], 2)

    return {
        "ok": True,
        "summary": {
            "total_products": len(products),
            "product_value": round(product_value, 2),
            "expected_earnings": round(expected_earnings, 2),
            "total_cost": round(total_cost, 2),
            "net_profit": round(net_profit, 2),
            "average_margin": round(
                sum(margins) / len(margins) if margins else 0.0,
                2,
            ),
            "by_category": by_category,
        },
    }


# -----------------------------
# Review / Runs / Tasks
# -----------------------------

@app.get("/api/review")
def review_queue():
    products = storage.products()
    return {
        "ok": True,
        "products": [
            p for p in products
            if p["status"] in {"collected", "verified", "rejected", "approved"}
        ],
    }


@app.post("/api/review/{product_id}/approve")
def approve_product(product_id: int):
    try:
        return {
            "ok": True,
            "product": storage.set_product_status(product_id, "approved", True),
        }
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)


@app.post("/api/review/{product_id}/reject")
def reject_product(product_id: int):
    try:
        return {
            "ok": True,
            "product": storage.set_product_status(product_id, "rejected", False),
        }
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

        run = storage.create_run(
            str(body.get("kind", "product_collection")),
            category,
            target,
        )
        task = storage.create_task(
            "product_collection",
            {
                "run_id": run["id"],
                "category": category,
                "target_count": target,
            },
        )
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
    return {
        "ok": True,
        "task": storage.create_task(
            kind,
            body.get("payload")
            if isinstance(body.get("payload"), dict)
            else {},
        ),
    }


@app.get("/api/stages")
def stages():
    return {
        "ok": True,
        "stages": {
            "content": [],
            "images": [],
            "pins": [],
        },
    }


@app.get("/api/audit")
def audit():
    return {"ok": True, "events": storage.audit_rows()}


app.mount(
    "/static",
    StaticFiles(directory=BASE / "app" / "static"),
    name="static",
)
