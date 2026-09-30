import {
  type AcquireResult,
  KIND_LABEL,
  type TCOBreakdown,
} from "@/lib/acquire";
import { formatMoney } from "@/lib/price-check";

function money(cents: number): string {
  return formatMoney(cents, "CAD");
}

function OptionRow({
  option,
  best,
}: {
  option: TCOBreakdown;
  best: boolean;
}) {
  return (
    <li className={best ? "acq-row acq-row-best" : "acq-row"}>
      <div className="acq-row-head">
        <span className="acq-kind">{KIND_LABEL[option.kind] ?? option.kind}</span>
        <span className="acq-label">{option.option_label}</span>
        <span className="acq-total">
          {money(option.effective_total_cents)}
          <span className="acq-permonth">
            {" "}
            · {money(option.monthly_equivalent_cents)}/mo
          </span>
        </span>
      </div>
      <p className="acq-breakdown">
        Device {money(option.upfront_cents + option.device_cost_cents)}
        {option.plan_cost_cents > 0 ? (
          <> · phone plan {money(option.plan_cost_cents)}</>
        ) : null}
        {option.resale_credit_cents > 0 ? (
          <> · resale value −{money(option.resale_credit_cents)}</>
        ) : null}
      </p>
      {option.assumptions.length > 0 ? (
        <ul className="acq-notes">
          {option.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * Layer 2 — how to acquire this product (buy outright / finance / lease /
 * refurbished), ranked by total cost of ownership over the horizon. Renders
 * nothing when the advisor had no answer.
 */
export function AcquireBlock({ data }: { data: AcquireResult | null }) {
  if (!data || data.recommendation.ranked.length === 0) return null;
  const { recommendation: rec, category } = data;
  const includesPlan = rec.ranked.some((o) => o.plan_cost_cents > 0);

  return (
    <section className="acq">
      <p className="acq-lead">
        Cheapest way to own it over {rec.horizon_months} months:{" "}
        <strong>{rec.best_label}</strong>
        {rec.runner_up_gap_cents > 0 ? (
          <> — next option costs {money(rec.runner_up_gap_cents)} more.</>
        ) : null}
      </p>
      <p className="acq-scope">
        {includesPlan
          ? `Totals are the full cost over ${rec.horizon_months} months: the device, an estimated phone plan, minus what you could resell it for at the end. They are not the phone's price.`
          : `Totals are the full cost over ${rec.horizon_months} months, minus what you could resell it for at the end.`}
      </p>

      <ul className="acq-list">
        {rec.ranked.map((o) => (
          <OptionRow
            key={o.option_label}
            option={o}
            best={o.option_label === rec.best_label}
          />
        ))}
      </ul>

      {rec.caveats.length > 0 ? (
        <ul className="acq-caveats">
          {rec.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}

      <details className="acq-verify">
        <summary>Check these yourself</summary>
        <ul>
          {rec.verify_first.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      </details>

      <p className="acq-note">
        Category read as <em>{category}</em>. Costs use estimated Canadian plan
        and financing terms — confirm current numbers before acting.
      </p>
    </section>
  );
}
