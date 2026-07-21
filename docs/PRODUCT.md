# Product

DealHunter helps users discover affiliate-supported product deals through search and future
AI-assisted recommendations. The product prioritizes trustworthy recommendations, clear merchant
attribution, explainable ranking, and transparent affiliate relationships.

## Current Scope

This repository contains the modular monolith foundation plus the affiliate domain model, mock
Canadian affiliate provider, ingestion pipeline, protected admin visibility endpoints, and a first
public product/offer search slice.

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
