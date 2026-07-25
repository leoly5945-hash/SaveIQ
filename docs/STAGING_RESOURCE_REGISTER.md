# Staging Resource Register

This file records Render staging resources after the Blueprint is applied. Do not add secrets,
tokens, passwords, private registry credentials, or database URLs.

## Render Workspace

| Field          | Value       |
| -------------- | ----------- |
| Workspace      | SaveIQ      |
| Environment    | staging     |
| Blueprint file | render.yaml |
| Last verified  | 2026-07-24  |
| Overall status | HEALTHY     |

## Services

| Resource          | Render ID                  | Hostname                                      | Image digest                                                              | Status    | Notes                                        |
| ----------------- | -------------------------- | --------------------------------------------- | ------------------------------------------------------------------------- | --------- | -------------------------------------------- |
| Frontend web      | TODO                       | `https://dealhunter-staging-web.onrender.com` | `sha256:daa1bf7ef762c6d740566c26949eeaf21e69085ceb517a4be3ce052c4e5fcc71` | HEALTHY   | Sends `X-Robots-Tag: noindex, nofollow`      |
| API backend       | `srv-d9e7qvbrjlhs73bt6tu0` | `https://dealhunter-staging-api.onrender.com` | `sha256:cf235ddd3ca1773231a98823fbc868ad6e0689530cb96d2d9efee81053bfd500` | HEALTHY   | `/health` returns 200 OK                     |
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
| `make staging-smoke`                               | PASS   | Output: `staging_smoke=ok`; 6 offers, 2 search results   |
| No production secrets or real integrations enabled | PASS   | Keep mock-only until staging gate passes                 |

## Post-Apply Notes

- Update this register only after Render resources exist and are healthy.
- Keep all secret values in Render environment settings, never in this document.
- Stop and investigate if Blueprint sync, migration, service boot, image digest, or secret prompts fail.
