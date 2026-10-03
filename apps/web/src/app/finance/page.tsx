import Link from "next/link";
import type { Metadata } from "next";

import { getSiteUrl } from "@/lib/config";
import { FINANCE_HUB_DESCRIPTION, FINANCE_HUB_ITEMS } from "@/lib/finance";

// Placeholder data lives under /finance/* until a real affiliate feed backs
// it (see lib/finance.ts). Keep this out of search results until then.
export const metadata: Metadata = {
  title: "Finance | SaveIQ",
  description: FINANCE_HUB_DESCRIPTION,
  alternates: { canonical: "/finance" },
  robots: { index: false, follow: false },
};

export default function FinanceHubPage() {
  const site = getSiteUrl();

  return (
    <main className="home-shell finance-hub-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>Finance</span>
      </nav>

      <h1 className="home-title">Know the Real Cost</h1>
      <p className="deal-page-blurb">{FINANCE_HUB_DESCRIPTION}</p>

      <div className="finance-hub-grid">
        {FINANCE_HUB_ITEMS.map((item) => (
          <Link key={item.vertical} href={`/finance/${item.vertical}`} className="finance-hub-card">
            <span className="finance-hub-card-title">
              {item.title}
              {item.isNew ? <span className="finance-hub-card-new">New</span> : null}
            </span>
            <p className="deal-page-disclosure">{item.description}</p>
          </Link>
        ))}
      </div>

      <p className="deal-page-back">
        <Link href="/deals">← Back to Deals</Link>
      </p>

      <p className="finance-disclosure">
        {site.replace(/^https?:\/\//, "")} may earn a commission when you sign up through a
        link on this page. See our <Link href="/about">About</Link> page for how we make
        money.
      </p>
    </main>
  );
}
