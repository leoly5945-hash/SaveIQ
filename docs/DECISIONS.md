# Decisions

## 2026-07-10: Use Modular Monolith

Status: Accepted

DealHunter starts as a modular monolith with clear internal package boundaries. This reduces
operational overhead while the product surface and data model are still forming.

## 2026-07-10: Use PostgreSQL With pgvector

Status: Accepted

PostgreSQL is the primary store and pgvector is enabled for future semantic retrieval. Vector fields
remain optional until the AI retrieval system is implemented.

## 2026-07-10: No Web Scraping

Status: Accepted

DealHunter will use approved APIs, feeds, or partner data access. Web scraping is outside the
intended architecture.

## 2026-07-18: Rename To DealHunter AI

Status: Accepted

The public product brand is DealHunter AI. Public branding is now exposed through configuration
where practical.

## 2026-07-18: Affiliate Connectors Are Provider Plugins

Status: Accepted

Future affiliate integrations should implement the provider adapter protocol and register with the
provider registry. Provider mapping must remain isolated from core product and offer logic.

## 2026-07-18: Deterministic Matching Only

Status: Accepted

Product resolution uses exact identifiers and brand plus MPN matching. LLM-based matching is deferred
until evaluation and review workflows exist.
