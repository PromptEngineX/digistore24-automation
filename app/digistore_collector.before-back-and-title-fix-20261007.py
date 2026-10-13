from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / "data" / "digiflow.sqlite3"
API_BASE = "http://127.0.0.1:8787"

MARKETPLACE = "https://www.digistore24-app.com/app/en/affiliate/account/marketplace/all"
APP_HOST = "https://www.digistore24-app.com"

# These are the six preferred internal categories.
# "All Categories" remains an aggregate scope, not a seventh quota.
CATEGORIES = [
    "Business & Investment",
    "Dating, Relationships & Romance",
    "Education",
    "Health & Fitness",
    "Family & Children",
    "Hobby & Craft",
]

# Classification is intentionally conservative: products that do not have
# a meaningful match are skipped rather than forced into a category.
CATEGORY_KEYWORDS = {
    "Business & Investment": (
        "business", "entrepreneur", "entrepreneurship", "startup", "invest",
        "investment", "trading", "forex", "stock", "crypto", "wealth", "finance",
        "money", "income", "marketing", "sales", "lead generation", "ecommerce",
        "shopify", "affiliate", "real estate", "property", "amazon fba",
        "dropshipping", "career", "job", "productivity", "management",
    ),
    "Dating, Relationships & Romance": (
        "dating", "relationship", "romance", "marriage", "married", "couple",
        "couples", "love", "attraction", "breakup", "divorce", "intimacy",
        "communication", "seduction", "dating app", "husband", "wife", "partner",
    ),
    "Education": (
        "course", "training", "education", "learn", "learning", "school", "study",
        "exam", "tutorial", "lesson", "language", "english", "math", "coding",
        "programming", "javascript", "python", "science", "teaching", "teacher",
        "certification", "academic", "ebook", "book", "masterclass", "skill",
    ),
    "Health & Fitness": (
        "health", "fitness", "workout", "exercise", "weight loss", "weight-loss",
        "diet", "nutrition", "supplement", "vitamin", "wellness", "muscle", "body",
        "yoga", "meditation", "sleep", "blood pressure", "cholesterol", "metabolism",
        "detox", "pain relief", "joint", "heart", "brain", "memory",
    ),
    "Family & Children": (
        "parent", "parenting", "child", "children", "baby", "toddler", "kid", "kids",
        "family", "pregnancy", "pregnant", "newborn", "mother", "father", "teen",
        "teenager", "education for kids", "family relationship",
    ),
    "Hobby & Craft": (
        "hobby", "craft", "sewing", "serger", "quilting", "knitting", "crochet",
        "woodworking", "gardening", "fishing", "photography", "painting", "drawing",
        "diy", "do it yourself", "cooking", "recipe", "baking", "music", "guitar",
        "piano", "handmade", "crafting", "collecting",
    ),
}

# Required for acceptance. Other marketplace fields are retained when present.
ESSENTIAL = (
    "external_id", "detail_url", "name", "price", "currency",
    "sales_page_url", "vendor", "commission_percent",
)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def absolute_url(value: str | None) -> str | None:
    value = clean(value)
    if not value:
        return None
    return urljoin(APP_HOST, value)

def parse_money(value: str | None):
    value = clean(value)
    if not value:
        return None, None
    m = re.search(
        r"([â‚¬$Â£â‚¹])\s*([0-9]+(?:[.,][0-9]+)?)|"
        r"([0-9]+(?:[.,][0-9]+)?)\s*([â‚¬$Â£â‚¹])",
        value,
    )
    if not m:
        return None, None
    symbol = m.group(1) or m.group(5)
    number = m.group(2) or m.group(3)
    currency = {"â‚¬": "EUR", "$": "USD", "Â£": "GBP", "â‚¹": "INR"}.get(symbol, symbol)
    try:
        return float(number.replace(",", "")), currency
    except ValueError:
        return None, currency

def parse_percent(value: str | None):
    if not value:
        return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", value)
    return float(m.group(1).replace(",", ".")) if m else None

def classify_product(name: str, product_type: str, description: str):
    text = clean(" ".join((name, product_type, description))).lower()
    scores = {}
    hits = {}
    for category, words in CATEGORY_KEYWORDS.items():
        matched = [w for w in words if w in text]
        hits[category] = matched[:12]
        scores[category] = len(matched)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return None, {"scores": scores, "hits": hits, "confidence": 0.0}

    top, second = ranked[0], ranked[1]
    confidence = min(1.0, top[1] / max(3, top[1] + second[1]))
    return top[0], {"scores": scores, "hits": hits, "confidence": confidence}

def add_query(url: str, **params) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for k, v in params.items():
        qs[k] = [str(v)]
    return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

class Registry:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS digistore_product_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT NOT NULL UNIQUE,
                detail_url TEXT NOT NULL,
                product_name TEXT,
                internal_category TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'seen',
                product_row_id INTEGER,
                run_id INTEGER,
                reason TEXT
            )
        """)
        self.db.commit()

    def seen(self, external_id: str) -> bool:
        row = self.db.execute(
            "SELECT status FROM digistore_product_registry "
            "WHERE external_id = ? LIMIT 1",
            (external_id,),
        ).fetchone()

        if not row:
            return False

        permanent_statuses = {
            "accepted",
            "accepted_fallback",
            "approved",
            "completed",
            "published",
            "skipped_api_duplicate",
        }

        return row[0] in permanent_statuses
    def record(self, product: dict, status="accepted", product_row_id=None,
               run_id=None, reason=None):
        ts = now_iso()
        self.db.execute("""
            INSERT INTO digistore_product_registry
            (external_id, detail_url, product_name, internal_category,
             first_seen_at, last_seen_at, status, product_row_id, run_id, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                status=excluded.status,
                product_row_id=COALESCE(
                    excluded.product_row_id,
                    digistore_product_registry.product_row_id
                ),
                run_id=COALESCE(excluded.run_id, digistore_product_registry.run_id),
                reason=excluded.reason
        """, (
            product["external_id"], product["detail_url"], product.get("name"),
            product.get("internal_category"), ts, ts, status,
            product_row_id, run_id, reason
        ))
        self.db.commit()

    def close(self):
        self.db.close()

def extract_external_id(url: str) -> str | None:
    m = re.search(r"/detail/([^/?#]+)", url)
    return m.group(1) if m else None

def parse_detail(page, detail_url: str, navigate: bool = True) -> dict:
    if navigate:
        page.goto(detail_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(500)
    body = page.locator("body").inner_text(timeout=10000)
    lines = [clean(x) for x in body.splitlines() if clean(x)]

    # Digistore24 renders the product title and product type together
    # inside the page h1. Use the DOM element directly rather than relying
    # on body-text position, which can place the footer before the title.
    name = None
    product_type = ""

    try:
        h1 = page.locator("h1").first
        if h1.count():
            h1_lines = [
                clean(x)
                for x in h1.inner_text(timeout=5000).splitlines()
                if clean(x)
            ]

            if h1_lines:
                name = h1_lines[0]

            if len(h1_lines) > 1:
                product_type = h1_lines[1]
    except Exception:
        pass

    # Conservative fallback if the h1 is temporarily unavailable.
    if not name:
        for i, line in enumerate(lines):
            if "All offers on the affiliate marketplace" in line:
                for candidate in lines[i + 1:i + 8]:
                    if candidate not in {
                        "My favorites on the affiliate marketplace",
                        "Back",
                    } and not candidate.startswith(("?", "$", "?", "?")):
                        name = candidate
                        break
                break

    def value_after(label):
        for i, line in enumerate(lines):
            if line.lower() == label.lower() and i + 1 < len(lines):
                return lines[i + 1]
        return None

    image_url = None
    imgs = page.locator("img")
    for i in range(min(imgs.count(), 20)):
        src = imgs.nth(i).get_attribute("src")
        if src and "/product/" in src:
            image_url = absolute_url(src)
            break

    sales_page_url = None
    affiliate_support_url = None
    links = page.locator("a")
    for i in range(links.count()):
        a = links.nth(i)
        txt = clean(a.inner_text())
        href = a.get_attribute("href")
        if txt == "Sales page" and href:
            sales_page_url = absolute_url(href)
        elif txt == "Affiliate support page" and href:
            affiliate_support_url = absolute_url(href)

    price = currency = None
    commission = earnings_cart = cart_conversion = cancellation = None
    vendor = online_since = payment_methods = None

    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if line == "Price":
            price, currency = parse_money(nxt)
        elif line == "Commission":
            commission = parse_percent(nxt)
        elif line == "Earnings/cart visitor*":
            earnings_cart, _ = parse_money(nxt)
        elif line == "Cart conversion*":
            cart_conversion = parse_percent(nxt)
        elif line == "Cancellation rate*":
            cancellation = parse_percent(nxt)
        elif line == "Vendor":
            vendor = nxt
        elif line == "Online since":
            online_since = nxt
        elif line == "Payment methods":
            payment_methods = nxt

    net_earnings = None
    for i, line in enumerate(lines):
        if "Net earnings/sale" in line and i + 1 < len(lines):
            net_earnings, _ = parse_money(lines[i + 1])
            if net_earnings is not None:
                break

    promotion_action = None
    for button_text in ("Promote now", "Request promotion", "Copy promo link"):
        if page.get_by_role("button", name=button_text, exact=True).count():
            promotion_action = button_text
            break

    partnership_text = ""
    for line in lines:
        low = line.lower()
        if "has already accepted your request" in low:
            partnership_text = line
            break

    # Capture the descriptive/promotional block without clicking any promo action.
    description = ""
    marker = False
    chunks = []
    for line in lines:
        if line in ("Sales page", "Affiliate support page"):
            marker = True
            continue
        if marker and line in ("Price", "Commission"):
            break
        if marker:
            chunks.append(line)
    description = clean(" ".join(chunks))

    return {
        "external_id": extract_external_id(detail_url),
        "detail_url": detail_url,
        "name": name or "",
        "product_type": product_type,
        "description": description,
        "product_image_url": image_url,
        "price": price,
        "currency": currency,
        "net_earnings_sale": net_earnings,
        "commission_percent": commission,
        "earnings_cart_visitor": earnings_cart,
        "cart_conversion_percent": cart_conversion,
        "cancellation_rate_percent": cancellation,
        "vendor": vendor,
        "online_since": online_since,
        "payment_methods": payment_methods,
        "sales_page_url": sales_page_url,
        "affiliate_support_url": affiliate_support_url,
        "promotion_action": promotion_action,
        "partnership_text": partnership_text,
        "marketplace_url": MARKETPLACE,
        "source": "Digistore24 Marketplace",
        "collected_at": now_iso(),
        "raw_detail_text": body[:12000],
    }

def essential_missing(product: dict) -> list[str]:
    return [k for k in ESSENTIAL if product.get(k) in (None, "", [])]

def post_product(product: dict, category: str, api_base: str):
    details = dict(product)
    details["internal_category"] = category
    details["digistore_product_type"] = product.get("product_type")
    details["category_rule"] = "preferred-six-with-fallback"

    payload = {
        "category": category,
        "name": product["name"],
        "url": product["sales_page_url"],
        "amount": str(product["price"]),
        "currency": product["currency"],
        "details": details,
    }
    response = requests.post(
        f"{api_base}/api/products", json=payload, timeout=30
    )
    if response.status_code == 409:
        return None, "api_duplicate"
    response.raise_for_status()
    return response.json().get("product"), None

def collect(target: int, api_base: str, max_pages: int,
            pause: float, dry_run: bool):
    registry = Registry(DB_PATH)
    selected = []
    counts = {c: 0 for c in CATEGORIES}
    counts["Other Eligible"] = 0
    fallback = []
    skipped = {
        "duplicate": 0,
        "missing": 0,
        "unclear_category": 0,
        "error": 0,
    }
    run_id = int(time.time())

    # Existing DigiFlow products are permanently used too.
    existing = set()
    try:
        response = requests.get(f"{api_base}/api/products/all", timeout=20)
        if response.ok:
            for product in response.json().get("products", []):
                details = product.get("details") or {}
                if details.get("external_id"):
                    existing.add(str(details["external_id"]))
    except Exception as exc:
        print(f"[WARN] Could not read existing DigiFlow products: {exc}")

    def wait_for_marketplace(page):
        page.wait_for_timeout(1800)

        # The Marketplace page itself is the authoritative return point.
        # Do not require product cards to be rendered before considering
        # the Marketplace restored.
        marketplace_host = "digistore24-app.com"
        marketplace_path = "/app/en/affiliate/account/marketplace/"

        def is_marketplace_url(url):
            return (
                marketplace_host in url
                and marketplace_path in url
                and "/detail/" not in url
            )

        if not is_marketplace_url(page.url):
            page.wait_for_timeout(1500)

        if not is_marketplace_url(page.url):
            raise RuntimeError(
                f"Marketplace was not restored. Current URL: {page.url}"
            )

        # Product cards are allowed to render asynchronously.
        page.wait_for_timeout(1000)

    def get_unique_detail_hrefs(page):
        links = page.locator('a[href*="/detail/"]')
        urls = []

        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            if not href:
                continue

            url = absolute_url(href)

            if url and "/detail/" in url and url not in urls:
                urls.append(url)

        return urls

    def click_detail(page, detail_url):
        # The href was discovered from the live Marketplace DOM.
        # We now click that actual Marketplace link rather than directly
        # navigating to a constructed product URL.
        locator = page.locator(
            f'a[href="{detail_url}"]'
        ).first

        if not locator.count():
            # Some hrefs can be relative in the live DOM.
            path = urlparse(detail_url).path
            locator = page.locator(
                f'a[href*="{path}"]'
            ).first

        if not locator.count():
            raise RuntimeError(
                f"Marketplace product link disappeared: {detail_url}"
            )

        locator.scroll_into_view_if_needed()
        locator.click(timeout=15000)

        page.wait_for_load_state(
            "domcontentloaded",
            timeout=45000,
        )

        try:
            page.locator("h1").first.wait_for(
                state="visible",
                timeout=15000,
            )
        except Exception:
            page.wait_for_timeout(2000)

    def return_to_marketplace(page, marketplace_url):
        # Return through the browser history first. This preserves the
        # authenticated browser session and normal Marketplace navigation.
        try:
            page.go_back(
                wait_until="domcontentloaded",
                timeout=45000,
            )
        except Exception:
            # If the SPA/browser history did not restore the Marketplace,
            # return to the exact Marketplace page that was being processed.
            page.goto(
                marketplace_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )

        wait_for_marketplace(page)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(
                "http://127.0.0.1:9222"
            )

            if not browser.contexts:
                raise RuntimeError(
                    "No Chrome context is available on CDP port 9222."
                )

            context = browser.contexts[0]

            pages = context.pages
            page = next(
                (
                    p for p in pages
                    if "digistore24-app.com" in p.url
                ),
                None,
            )

            if page is None:
                page = context.new_page()

            # Enter the real Marketplace once. From this point onward,
            # product navigation and pagination use the live UI links.
            marketplace_url = add_query(
                MARKETPLACE,
                **{"language[]": "en", "page": 1},
            )

            print("[BROWSER] Opening Digistore24 Marketplace...")
            page.goto(
                marketplace_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )

            wait_for_marketplace(page)

            current_page = 1

            while current_page <= max_pages:
                if len(selected) >= target:
                    break

                print(
                    f"[COLLECT] Marketplace page "
                    f"{current_page}/{max_pages}"
                )

                list_url = page.url
                urls = get_unique_detail_hrefs(page)

                print(
                    f"[BROWSER] Found {len(urls)} unique "
                    f"product cards on page {current_page}"
                )

                if not urls:
                    print("[STOP] No product detail links found.")
                    break

                for detail_url in urls:
                    if len(selected) >= target:
                        break

                    external_id = extract_external_id(detail_url)

                    if not external_id:
                        skipped["missing"] += 1
                        continue

                    if (
                        external_id in existing
                        or registry.seen(external_id)
                    ):
                        skipped["duplicate"] += 1
                        print(
                            f"[SKIP] Duplicate product {external_id}"
                        )
                        continue

                    try:
                        # ---- Marketplace card -> product detail ----
                        print(
                            f"[BROWSER] Opening product "
                            f"{external_id}"
                        )

                        click_detail(page, detail_url)

                        current_detail_url = page.url

                        product = parse_detail(
                            page,
                            current_detail_url,
                            navigate=False,
                        )

                        # The detail page itself is the authoritative
                        # product URL discovered by the browser.
                        product["detail_url"] = current_detail_url
                        product["external_id"] = (
                            extract_external_id(current_detail_url)
                            or external_id
                        )

                        if (
                            product["external_id"] in existing
                            or registry.seen(product["external_id"])
                        ):
                            skipped["duplicate"] += 1
                            return_to_marketplace(
                                page,
                                list_url,
                            )
                            continue

                        missing = essential_missing(product)

                        if missing:
                            skipped["missing"] += 1

                            registry.record(
                                product,
                                status="skipped_missing",
                                run_id=run_id,
                                reason="Missing: "
                                + ", ".join(missing),
                            )

                            print(
                                f"[SKIP] Missing fields: "
                                f"{', '.join(missing)}"
                            )

                            return_to_marketplace(
                                page,
                                list_url,
                            )
                            continue

                        category, evidence = classify_product(
                            product["name"],
                            product["product_type"],
                            product["description"],
                        )

                        product["classification"] = evidence

                        # A product that cannot be confidently assigned
                        # to one of the six preferred categories is held
                        # as an eligible fallback candidate.
                        if category is None:
                            product["internal_category"] = (
                                "Other Eligible"
                            )
                            fallback.append(product)

                            print(
                                "[HOLD] Other Eligible | "
                                f"{product['name']}"
                            )

                            return_to_marketplace(
                                page,
                                list_url,
                            )
                            continue

                        product["internal_category"] = category

                        # Preferred categories get up to 10 products.
                        # Extra valid products remain available as fallback.
                        if counts[category] >= 10:
                            fallback.append(product)

                            print(
                                f"[HOLD] {category} quota full | "
                                f"{product['name']}"
                            )

                            return_to_marketplace(
                                page,
                                list_url,
                            )
                            continue

                        row = None

                        if not dry_run:
                            row, err = post_product(
                                product,
                                category,
                                api_base,
                            )

                            if err == "api_duplicate":
                                existing.add(
                                    product["external_id"]
                                )

                                registry.record(
                                    product,
                                    status="skipped_api_duplicate",
                                    run_id=run_id,
                                    reason=(
                                        "Already present in "
                                        "DigiFlow"
                                    ),
                                )

                                skipped["duplicate"] += 1

                                return_to_marketplace(
                                    page,
                                    list_url,
                                )
                                continue

                        selected.append(product)
                        counts[category] += 1
                        existing.add(product["external_id"])

                        if not dry_run:
                            registry.record(
                                product,
                                status="accepted",
                                product_row_id=(
                                    (row or {}).get("id")
                                    if row
                                    else None
                                ),
                                run_id=run_id,
                            )

                        print(
                            f"[ACCEPT] {category} | "
                            f"{product['name']} | "
                            f"{product['price']} "
                            f"{product['currency']}"
                        )

                        # ---- Product detail -> Marketplace ----
                        return_to_marketplace(
                            page,
                            list_url,
                        )

                    except PlaywrightTimeoutError as exc:
                        skipped["error"] += 1

                        print(
                            f"[WARN] Detail timeout: "
                            f"{detail_url} | {exc}"
                        )

                        try:
                            return_to_marketplace(
                                page,
                                list_url,
                            )
                        except Exception as return_exc:
                            print(
                                "[WARN] Could not restore "
                                f"Marketplace: {return_exc}"
                            )

                    except Exception as exc:
                        skipped["error"] += 1

                        print(
                            f"[WARN] Detail failed: "
                            f"{detail_url} | {exc}"
                        )

                        try:
                            return_to_marketplace(
                                page,
                                list_url,
                            )
                        except Exception as return_exc:
                            print(
                                "[WARN] Could not restore "
                                f"Marketplace: {return_exc}"
                            )

                    time.sleep(pause)

                if len(selected) >= target:
                    break

                # ---- Marketplace pagination through the live UI ----
                next_page = current_page + 1

                if next_page > max_pages:
                    break

                next_href = None

                pagination_links = page.locator(
                    'a[href*="page="]'
                )

                for i in range(pagination_links.count()):
                    href = pagination_links.nth(i).get_attribute(
                        "href"
                    )

                    if not href:
                        continue

                    candidate = absolute_url(href)

                    if not candidate:
                        continue

                    query = parse_qs(
                        urlparse(candidate).query
                    )

                    values = query.get("page", [])

                    if values and str(next_page) in values:
                        next_href = candidate
                        break

                if not next_href:
                    print(
                        f"[STOP] Could not find live pagination "
                        f"link for page {next_page}."
                    )
                    break

                print(
                    f"[BROWSER] Clicking Marketplace page "
                    f"{next_page}"
                )

                next_locator = page.locator(
                    f'a[href="{next_href}"]'
                ).first

                if not next_locator.count():
                    path = urlparse(next_href).path
                    next_locator = page.locator(
                        f'a[href*="{path}"]'
                    ).first

                if not next_locator.count():
                    print(
                        "[STOP] Pagination link disappeared."
                    )
                    break

                next_locator.scroll_into_view_if_needed()
                next_locator.click(timeout=15000)

                page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=45000,
                )

                wait_for_marketplace(page)

                current_page = next_page

            # If preferred categories could not reach 10, fill the
            # remaining target from valid fallback candidates.
            if len(selected) < target:
                print(
                    "[FALLBACK] Filling remaining target from "
                    "held eligible products..."
                )

                for product in fallback:
                    if len(selected) >= target:
                        break

                    external_id = product.get("external_id")

                    if (
                        not external_id
                        or external_id in existing
                    ):
                        continue

                    category = product["internal_category"]

                    if not dry_run:
                        row, err = post_product(
                            product,
                            category,
                            api_base,
                        )

                        if err == "api_duplicate":
                            existing.add(external_id)
                            skipped["duplicate"] += 1
                            continue
                    else:
                        row = None

                    selected.append(product)
                    counts[category] += 1
                    existing.add(external_id)

                    if not dry_run:
                        registry.record(
                            product,
                            status="accepted_fallback",
                            product_row_id=(
                                (row or {}).get("id")
                                if row
                                else None
                            ),
                            run_id=run_id,
                        )

                    print(
                        f"[ACCEPT-FALLBACK] "
                        f"{category} | {product['name']}"
                    )

    finally:
        registry.close()

    result = {
        "run_id": run_id,
        "target": target,
        "collected": len(selected),
        "category_counts": counts,
        "fallback_candidates_used": max(
            0,
            len(selected)
            - sum(min(v, 10) for v in counts.values()),
        ),
        "skipped": skipped,
        "dry_run": dry_run,
        "completed_at": now_iso(),
    }

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    return result

def main():
    parser = argparse.ArgumentParser(
        description="DigiFlow Digistore24 product collector"
    )
    parser.add_argument("--target", type=int, default=60)
    parser.add_argument("--max-pages", type=int, default=124)
    parser.add_argument("--pause", type=float, default=0.25)
    parser.add_argument("--api", default=API_BASE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.target <= 60:
        raise SystemExit("--target must be between 1 and 60")

    collect(
        target=args.target,
        api_base=args.api.rstrip("/"),
        max_pages=args.max_pages,
        pause=args.pause,
        dry_run=args.dry_run,
    )

if __name__ == "__main__":
    main()







