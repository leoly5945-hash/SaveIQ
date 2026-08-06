# Bandit Design (Gate 7)

## Goal

Optimize AI router provider selection (OpenAI / Anthropic / Mock) using a contextual bandit
that observes request features, chooses an arm, and updates from a scalar reward.

## Safety Modes

| Mode | Behavior |
|---|---|
| `disabled` | No bandit calls; rule-based router only |
| `logging` | Bandit proposes an action; **rule-based action is executed**; both logged |
| `active` | Bandit action applied only when `ready`; else rule-based fallback |

Default: feature off + mode `disabled`.

## Features (v0)

Fixed-length vector (`FEATURE_NAMES`):

1. `bias`
2. `query_len_norm`
3. `word_count_norm`
4. `complexity_simple` / `medium` / `complex`
5. `intent_recommendation` / `intent_search`
6. `market_ca`
7. `hour_sin` / `hour_cos`
8. `has_user_id`

Math collaborators may extend / reweight this set; keep dimension stable or version the
feature schema before changing production logs.

## Algorithm

**Disjoint LinUCB** (one linear model per action):

- Maintain \(A_a = I + \sum x x^\top\), \(b_a = \sum r x\)
- Score \(x^\top \hat\theta_a + \alpha \sqrt{x^\top A_a^{-1} x}\)
- Epsilon-greedy explore with `BANDIT_EPSILON` (default 0.1)

Implemented in pure Python for a small feature dimension; no Vowpal Wabbit / numpy required
in Gate 7.

## Reward (heuristic v0)

\[
r = \alpha q + \beta (1 - c_{\mathrm{norm}}) + \gamma (1 - \ell_{\mathrm{norm}})
\]

- \(q\): parser confidence (0 on failure)
- \(c_{\mathrm{norm}}\): estimated USD cost / `0.05`
- \(\ell_{\mathrm{norm}}\): latency ms / `5000`

Defaults: α=0.5, β=0.3, γ=0.2. No automatic budget hard-stop.

## Logging Schema (`bandit_logs`)

- `features` (JSON), `action`, `reward`, `user_id`, `created_at`
- Plus: `rule_action`, `bandit_action`, `mode`, `applied`, `explored`, cost/latency/confidence,
  `metadata` (scores, breakdown)

## Offline Evaluation

`POST /admin/bandit/train` loads rewarded logs, trains the live agent, and runs a progressive
replay that records:

- cumulative reward under bandit choices (only when matching logged action)
- rule-based cumulative reward proxy
- agreement rate / simple regret vs logged policy

This is an interim proxy until IPS/DR estimators are added with the math team.

## Online Deployment Checklist

1. Enable `logging` and collect ≥ thousands of rewarded rows.
2. Run offline train + review metrics.
3. Enable `active` with conservative epsilon.
4. A/B against rule-based; keep Feature flag kill-switch.
