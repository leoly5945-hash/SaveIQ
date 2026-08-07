# Staging Resource Register

This file records Render staging resources after the Blueprint is applied. Do not add secrets,
tokens, passwords, private registry credentials, or database URLs.

## Render Workspace

| Field          | Value       |
| -------------- | ----------- |
| Workspace      | SaveIQ      |
| Environment    | staging     |
| Blueprint file | render.yaml |
| Last verified  | 2026-08-07  |
| Overall status | HEALTHY     |

## Services

| Resource          | Render ID                  | Hostname                                      | Image digest                                                              | Status    | Notes                                        |
| ----------------- | -------------------------- | --------------------------------------------- | ------------------------------------------------------------------------- | --------- | -------------------------------------------- |
| Frontend web      | TODO                       | `https://dealhunter-staging-web.onrender.com` | `sha256:7cf2997dc3e3378f1f9896e33bbf8e58d4f3f0cbe52466a8da71d0c533896a02` | HEALTHY   | Gate 9 pin; sends `X-Robots-Tag: noindex, nofollow` |
| API backend       | `srv-d9e7qvbrjlhs73bt6tu0` | `https://dealhunter-staging-api.onrender.com` | `sha256:9f6de983690a5b4a3c2dedf4076127cc8d1535c410c19795423d42c20ef2b1d1` | HEALTHY   | Gate 9 pin; OpenAPI exposes Gates 6B–9 paths |
| PostgreSQL        | TODO                       | n/a                                           | n/a                                                                       | AVAILABLE | Free staging database; expires after 30 days |
| Redis / Key Value | TODO                       | n/a                                           | n/a                                                                       | AVAILABLE | Free in-memory staging cache                 |
| Background worker | Deferred                   | n/a                                           | n/a                                                                       | Deferred  | Add after staging gate if needed             |
| Scheduler         | Deferred                   | n/a                                           | n/a                                                                       | Deferred  | Add after staging gate if needed             |

## Validation Evidence

| Check                                              | Result | Notes                                                    |
| -------------------------------------------------- | ------ | -------------------------------------------------------- |
| Blueprint applied from `render.yaml`               | PASS   | Blueprint ID: `exs-d9e7acf41pts73ecmndg`                 |
| `make staging-provision-validate`                  | PASS   | Output: `staging_provisioning_validation=ok`             |
| Frontend health                                    | PASS   | `https://dealhunter-staging-web.onrender.com/api/health` |
| API health                                         | PASS   | `https://dealhunter-staging-api.onrender.com/health`     |
| Staging noindex header                             | PASS   | `X-Robots-Tag: noindex, nofollow`                        |
| `make staging-smoke`                               | PASS   | `staging_smoke=ok`; offers=6; search=2; eval 4/0         |
| Gate 9 admin/public checks                         | PASS   | Router/bandit/personalization/models off; benchmark 40/5 |
| No production secrets or real integrations enabled | PASS   | Gate 6–9 feature flags remain disabled on staging        |

## Post-Apply Notes

- Update this register only after Render resources exist and are healthy.
- Keep all secret values in Render environment settings, never in this document.
- Stop and investigate if Blueprint sync, migration, service boot, image digest, or secret prompts fail.
