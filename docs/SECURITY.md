# Security

DealHunter handles commerce data, affiliate links, and future user preferences. The platform should be designed with conservative defaults from the start.

## Foundation Practices

- Environment variables are documented through examples only.
- Secrets are excluded from source control.
- CORS defaults to local frontend development.
- Affiliate provider code is isolated behind interfaces.
- Mock click tracking stores no user accounts, IP addresses, payment identifiers, or real affiliate
  conversion data.

## Future Requirements

- Validate and sanitize outbound affiliate URLs.
- Store partner credentials in a managed secret store.
- Add authentication before user-specific features.
- Rate-limit public endpoints.
- Log security-relevant events without sensitive payloads.
- Review data retention for recommendation traces and click events before production.

## Dependency Management

CI should run linting, type checks, builds, and tests. Dependency scanning should be added before production deployment.
