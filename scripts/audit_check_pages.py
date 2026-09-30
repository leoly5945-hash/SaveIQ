"""Audit prod /check pages across many real products and flag every known bug class.

Run: python3 scripts/audit_check_pages.py [--all] [ASIN ...]
With no ASINs it audits a 15-product sample of the curated deals + showcase
products (--all for every one). Stdlib only.

Every check spends Keepa tokens shared with real shoppers (refill ~20/min), so
products are audited one at a time with a pause, and the run stops at the first
Keepa 429 instead of draining the quota.
Each product is fetched twice: the API JSON (what the engine decided) and the
rendered page text (what the shopper reads), and the two are checked against
each other.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
import time
from pathlib import Path

API = "https://dealhunter-production-api.onrender.com/check?narrate=1&product_id="
WEB = "https://www.saveiq.ca/check/"
ROOT = Path(__file__).resolve().parents[1]

PHONE_ONLY = re.compile(
    r"\b(carrier|BYOD|battery health|current-flagship|gift-card bundles|trade-in credit|"
    r"device financing|unlocked|5G|unlimited\" plan|throttle)\b",
    re.I,
)
PHONE_CATEGORIES = {"smartphone", "cellular_tablet", "cellular_watch", "tablet"}
FIRST_PERSON = re.compile(r"\b(I|I'd|I'm|I've|I would|my)\b")
SAYS_WAIT = re.compile(r"\b(hold off|wait for|worth waiting|might wait|better to wait|you could wait)\b", re.I)
SAYS_BUY_NOW = re.compile(r"(?<!only )\b(buy (it )?now|go ahead and buy|grab it|great deal)\b", re.I)
PAUSE_SECONDS = 30
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")


def _get(url: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "saveiq-audit/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _page_text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    m = re.search(r"<main.*?</main>", raw, flags=re.S)
    raw = m.group(0) if m else raw
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _all_cents(obj, out: set[int]) -> set[int]:
    if isinstance(obj, dict):
        for v in obj.values():
            _all_cents(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _all_cents(v, out)
    elif isinstance(obj, int) and not isinstance(obj, bool):
        out.add(obj)
    elif isinstance(obj, float):
        out.add(round(obj * 100))
    elif isinstance(obj, str):
        for n in re.findall(r"\d+\.\d{2}", obj):
            out.add(round(float(n) * 100))
    return out


def audit(asin: str) -> dict:
    problems: list[str] = []
    try:
        d = json.loads(_get(API + asin))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return {"asin": asin, "error": f"api: {exc}", "keepa_429": "HTTP 429" in body}
    except Exception as exc:  # noqa: BLE001
        return {"asin": asin, "error": f"api: {exc}"}
    try:
        page = _page_text(_get(WEB + asin))
    except Exception as exc:  # noqa: BLE001
        page = ""
        problems.append(f"page fetch failed: {exc}")

    a = d.get("assessment") or {}
    verdict = a.get("verdict", "?")
    title = d.get("title") or ""
    narr = d.get("narration") or ""
    intel = a.get("intelligence") or {}
    w90 = (intel.get("windows") or {}).get("90") or {}
    ref = (d.get("comparison") or {}).get("reference_price_cents") or a.get(
        "effective_price", {}
    ).get("effective_cents")

    # 1. narration must agree with the badge, no first person, no invented numbers
    if narr:
        if verdict in ("FAIR", "BUY") and SAYS_WAIT.search(narr):
            problems.append(f"narration says wait but verdict is {verdict}")
        if verdict == "WAIT" and SAYS_BUY_NOW.search(narr):
            problems.append("narration says buy now but verdict is WAIT")
        if FIRST_PERSON.search(narr):
            problems.append("narration uses first person")
        known = _all_cents(d, set())
        for m in MONEY.findall(narr):
            c = round(float(m.replace(",", "")) * 100)
            if not any(abs(c - k) <= 1 for k in known):
                problems.append(f"narration cites ${m}, not in the data")

    # 2. page copy bugs
    if page:
        badge = re.search(r"Price check (Buy|Fair|Wait|BUY|FAIR|WAIT)\b", page)
        if not badge:
            problems.append("no verdict badge found on page")
        elif badge.group(1).upper() != verdict:
            problems.append(f"page badge {badge.group(1)} != api verdict {verdict}")
        for pat, label in [
            (r"\b1 other new sellers\b", "plural '1 other new sellers'"),
            (r"\bwithin \d", "missing $ in 'within N'"),
            (r"\b(NaN|undefined|\[object Object\])\b", "raw JS value on page"),
            (r"\$0\.00\b", "$0.00 shown"),
            (r"\bnull\b", "'null' on page"),
        ]:
            if re.search(pat, page):
                problems.append(label)
        cat = re.search(r"Category read as ([\w_]+)", page)
        cat_name = cat.group(1) if cat else None
        if cat_name and cat_name not in PHONE_CATEGORIES:
            hit = PHONE_ONLY.search(page)
            if hit:
                problems.append(f"phone-only copy '{hit.group(0)}' on a {cat_name} item")
        if re.search(r"\b(renewed|refurbished)\b", title, re.I) and re.search(
            r"Cheapest way to own it[^.]*: Amazon Renewed", page
        ):
            problems.append("renewed listing recommends 'Amazon Renewed' as the alternative")
        lo = re.search(r"90-day low \$([\d,]+\.\d{2})", page)
        if lo and w90.get("min_cents"):
            c = round(float(lo.group(1).replace(",", "")) * 100)
            if abs(c - w90["min_cents"]) > 1:
                problems.append(f"page 90-day low ${lo.group(1)} != data {w90['min_cents'] / 100:.2f}")

    # 3. offers that can't be right
    sp = d.get("spread") or {}
    for t in sp.get("tiers") or []:
        if ref and t["lowest_total_cents"] < 0.5 * ref:
            problems.append(
                f"{t['condition']} seller at {t['lowest_total_cents'] / 100:.2f} "
                f"< half of {ref / 100:.2f}"
            )
    comp = d.get("comparison") or {}
    for o in comp.get("offers") or []:
        if ref and not (0.5 * ref <= o["price_cents"] <= 2 * ref):
            problems.append(f"comparison {o['merchant']} {o['price_cents'] / 100:.2f} vs {ref / 100:.2f}")
    if "tag=saveiq-20" not in (d.get("buy_url") or ""):
        problems.append("buy link missing affiliate tag")

    return {"asin": asin, "verdict": verdict, "title": title[:70], "narration": narr,
            "problems": problems}


def default_asins() -> list[str]:
    deals = json.loads((ROOT / "apps/api/app/services/affiliate/curated_deals.json").read_text())
    deals = deals if isinstance(deals, list) else deals.get("deals", [])
    showcase = re.findall(r"B0[A-Z0-9]{8}", (ROOT / "apps/web/src/lib/showcase-products.ts").read_text())
    seen: dict[str, None] = {}
    for a in [x["asin"] for x in deals] + showcase + ["B01FWAZEIU"]:
        seen.setdefault(a, None)
    return list(seen)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--all"]
    asins = args or default_asins()
    if not args and "--all" not in sys.argv:
        asins = asins[:: max(1, len(asins) // 15)][:15]
    results = []
    for i, asin in enumerate(asins):
        if i:
            time.sleep(PAUSE_SECONDS)
        r = audit(asin)
        results.append(r)
        if r.get("keepa_429"):
            print(f"Keepa is out of tokens — stopping after {i + 1} products.")
            break
    bad = 0
    for r in results:
        if r.get("error"):
            print(f"ERR  {r['asin']}: {r['error']}")
            bad += 1
        elif r["problems"]:
            bad += 1
            print(f"FAIL {r['asin']} [{r['verdict']}] {r['title']}")
            for p in r["problems"]:
                print(f"       - {p}")
        else:
            print(f"ok   {r['asin']} [{r['verdict']}] {r['title']}")
    print(f"\n{len(results) - bad}/{len(results)} clean")
    Path("audit_results.json").write_text(json.dumps(results, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
