import Link from "next/link";

import { type AlternativesResult } from "@/lib/alternatives";
import { formatMoney } from "@/lib/price-check";

/**
 * "Buy this instead" — similar products that are a good buy right now. Only
 * shown for a WAIT / UNKNOWN verdict; renders nothing when none were found.
 */
export function AlternativesBlock({ data }: { data: AlternativesResult | null }) {
  if (!data || data.alternatives.length === 0) return null;

  return (
    <section className="alt">
      <p className="alt-lead">Rather not wait? These are a good buy right now:</p>
      <ul className="alt-list">
        {data.alternatives.map((a) => (
          <li key={a.product_id} className="alt-row">
            <div className="alt-row-head">
              <span className={`alt-badge alt-badge-${a.verdict.toLowerCase()}`}>
                {a.verdict}
              </span>
              <Link className="alt-title" href={`/check/${a.product_id}`}>
                {a.title}
              </Link>
              <span className="alt-price">
                {formatMoney(a.price_cents, a.currency)}
              </span>
            </div>
            {a.reason ? <p className="alt-reason">{a.reason}</p> : null}
          </li>
        ))}
      </ul>
      <p className="alt-note">
        Matched by category and price. Open one for its full verdict.
      </p>
    </section>
  );
}
