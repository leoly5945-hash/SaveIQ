# Discovery (Layer 3 — entry)

Layer 1 is "is this price good", Layer 2 is "how should I get it". Layer 3 is the
front door: a shopper types **what they want in words** instead of pasting a
link.

```
"power bank under $100"
   │  parse_shopping_query  (rules today; LLM via app/services/router later)
   ▼
ShoppingQuery{ search_terms: "power bank", price_max_cents: 10000 }
   │  discover()  — Keepa /search, then a concurrent price probe on the top few
   ▼
DiscoverResult{ hits: [ {product_id, title, price_cents?, in_budget?}, … ] }
   │  shopper clicks a hit → /check/<asin>
   ▼
verdict + sparkline + Amazon spread + comparison + acquisition paths
```

## Pieces

`app/services/discovery/`

| module | what |
| --- | --- |
| `query.py` | `parse_shopping_query(raw)` — **rule-based**. Pulls a budget out of "under / below / over / above / between / around $N" (and a trailing "$N" / "$N budget"), strips filler and stray numbers, keeps specs like `4k` / `1080p`. When it can't tell, it returns the cleaned text and no budget — a safe degrade. The loose long tail ("something around 2k-ish") is what the LLM parser is for. |
| `discover.py` | `discover(registry, query, limit)` — one Keepa `/search` call, then a **concurrent** current-price probe on the top ~6 candidates so every row shows a price (a storefront with blank prices reads as broken). A budget, when present, also filters/reorders (in-budget first, price asc; unpriced last). No verdict here — that costs 2+ Keepa calls each and belongs on `/check`. |

## Endpoint

`GET /discover?q=<natural language>&limit=8` — public, per-IP rate limited hard
(`DISCOVER_RATE_PER_MINUTE`, default **6** — it spends a search + a few price
calls). Returns the parsed `ShoppingQuery` + the ranked `hits`.

Web: `<DiscoverBox>` is the homepage's primary input (natural-language search);
the paste-a-link `<CheckBox>` sits below it under "Already looking at something on
Amazon.ca?". Each hit links to `/check/<asin>`.

## Not done yet (needs an LLM provider key)

* **LLM query parsing** for the phrasing the rules miss — wire `parse_shopping_query`
  `mode="llm"` through `app/services/router` (`AiRouter`). Providers already
  implemented: OpenAI, Anthropic, DeepSeek, Qwen, Ernie. Needs one of
  `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / … set, plus
  `FEATURE_LLM_INTENT_PARSER=true`. The current `LlmParsedIntent` contract is
  shaped for the old affiliate product (coupon/cashback/freshness) — a new
  shopping-query schema is needed.
* **LLM narration** of a `/check` result — one plain-language paragraph + a
  follow-up Q&A, again via `AiRouter`.
* **"buy this instead"** — when a verdict is WAIT, run `discover` on the same
  category and surface a BUY-verdict alternative.
