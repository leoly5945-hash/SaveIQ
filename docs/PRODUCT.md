# Product

DealHunter helps users discover affiliate-supported product deals through search and future
AI-assisted recommendations. The product prioritizes trustworthy recommendations, clear merchant
attribution, explainable ranking, and transparent affiliate relationships.

## Current Scope

This repository contains the modular monolith foundation plus the affiliate domain model, mock
Canadian affiliate provider, ingestion pipeline, protected admin visibility endpoints, a first
public product/offer search slice, and lightweight mock click tracking.

## Out of Scope

- Web scraping
- Real affiliate network integrations
- A complete AI agent
- Production deployment

## Initial User Jobs

- Search for products or deal categories.
- Compare normalized offers from approved affiliate sources.
- Understand merchant and source attribution.
- Review price history, coupons, and cashback opportunities.

## Phase 2 Search Slice

The first search experience is intentionally small and source-backed. It searches stored normalized
mock offers and supports filters for merchant, brand, category, coupon availability, cashback
availability, and freshness. Results can be sorted by current price or merchant and include simple
match reasons so the staging UI can explain why an offer appeared. Quick searches are limited to
terms represented in the seeded mock feed. Offer detail shows mock commercial context, source
attribution, price history, and coupon/cashback availability. It does not perform web scraping, call
real affiliate networks, or use an AI agent.

## Mock Click Tracking

The staging UI records best-effort clicks for mock product URLs and mock affiliate URLs. This helps
validate the product flow and attribution model before any real affiliate partner is connected. It
does not track conversions, scrape merchant pages, or send data to external affiliate networks.
An admin-only staging panel summarizes total clicks, product vs affiliate clicks, top offers, top
merchants, and recent mock click events.
Search results also expose mock click counts and can be sorted by most-clicked offers so staging can
test a basic feedback loop without introducing personalized tracking or real conversion data.
