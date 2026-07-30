# Security

DealHunter handles commerce data, affiliate links, and future user preferences. The platform should be designed with conservative defaults from the start.

## Foundation Practices

- Environment variables are documented through examples only.
- Secrets are excluded from source control.
- CORS defaults to local frontend development.
- Affiliate provider code is isolated behind interfaces.
- Mock click tracking stores no user accounts, IP addresses, payment identifiers, or real affiliate
  conversion data.
- Recommendation trace events store no user accounts, IP addresses, tokens, model prompts, or model
  responses.
- Gate 5A LLM parser artifacts are contract-only and must not include admin tokens, raw secrets,
  scraping output, live affiliate payloads, or model calls.
- Gate 5B OpenAI settings default to disabled. `OPENAI_API_KEY` must remain a secret, and parser
  tests must use injected mock clients instead of live model calls.
- Gate 5C route integration must preserve deterministic fallback unless the feature flag and parser
  client are explicitly enabled. Disabled staging traces may record parser fallback metadata but must
  not store raw model prompts or responses.

## Future Requirements

- Validate and sanitize outbound affiliate URLs.
- Store partner credentials in a managed secret store.
- Add authentication before user-specific features.
- Rate-limit public endpoints.
- Log security-relevant events without sensitive payloads.
- Review data retention for recommendation traces and click events before production.

## Dependency Management

CI should run linting, type checks, builds, and tests. Dependency scanning should be added before production deployment.
