# Staging Resource Register

This file records Render staging resources after the Blueprint is applied. Do not add secrets,
tokens, passwords, private registry credentials, or database URLs.

## Render Workspace

| Field          | Value       |
| -------------- | ----------- |
| Workspace      | SaveIQ      |
| Environment    | staging     |
| Blueprint file | render.yaml |
| Last verified  | TODO        |
| Overall status | TODO        |

## Services

| Resource          | Render ID | Hostname | Image digest  | Status   | Notes                                        |
| ----------------- | --------- | -------- | ------------- | -------- | -------------------------------------------- |
| Frontend web      | TODO      | TODO     | `sha256:TODO` | TODO     | Must send `X-Robots-Tag: noindex, nofollow`  |
| API backend       | TODO      | TODO     | `sha256:TODO` | TODO     | `/health` must be healthy                    |
| PostgreSQL        | TODO      | n/a      | n/a           | TODO     | Free staging database; expires after 30 days |
| Redis / Key Value | TODO      | n/a      | n/a           | TODO     | Free in-memory staging cache                 |
| Background worker | Deferred  | n/a      | n/a           | Deferred | Add after staging gate if needed             |
| Scheduler         | Deferred  | n/a      | n/a           | Deferred | Add after staging gate if needed             |

## Validation Evidence

| Check                                              | Result | Notes                                                 |
| -------------------------------------------------- | ------ | ----------------------------------------------------- |
| Blueprint applied from `render.yaml`               | TODO   | Use Blueprint, not manual services                    |
| `make staging-provision-validate`                  | TODO   | Expected output: `staging_provisioning_validation=ok` |
| Frontend health                                    | TODO   | `https://<web-host>/api/health`                       |
| API health                                         | TODO   | `https://<api-host>/health`                           |
| Staging noindex header                             | TODO   | `X-Robots-Tag: noindex, nofollow`                     |
| No production secrets or real integrations enabled | TODO   | Keep mock-only until staging gate passes              |

## Post-Apply Notes

- Update this register only after Render resources exist and are healthy.
- Keep all secret values in Render environment settings, never in this document.
- Stop and investigate if Blueprint sync, migration, service boot, image digest, or secret prompts fail.
