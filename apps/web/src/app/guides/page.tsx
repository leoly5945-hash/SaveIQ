import Link from "next/link";
import type { Metadata } from "next";

import { getSiteUrl } from "@/lib/config";
import { GUIDES, guidePath } from "@/lib/guides";

export const dynamic = "force-static";

const DESCRIPTION =
  "Plain, factual buying guides for Canadian shoppers — how to spot a real price, what the specs mean, and what you actually need.";

export const metadata: Metadata = {
  title: "Buying guides for Canadian shoppers | SaveIQ",
  description: DESCRIPTION,
  alternates: { canonical: "/guides" },
  openGraph: {
    title: "SaveIQ buying guides",
    description: DESCRIPTION,
    url: `${getSiteUrl()}/guides`,
    type: "website",
  },
};

export default function GuidesPage() {
  return (
    <main className="home-shell guides-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>Guides</span>
      </nav>

      <h1 className="home-title guides-page-title">Buying guides</h1>
      <p className="guides-page-intro">{DESCRIPTION}</p>

      <ul className="guides-list">
        {GUIDES.map((guide) => (
          <li className="guide-card" key={guide.slug}>
            <h2 className="guide-card-title">
              <Link href={guidePath(guide.slug)}>{guide.title}</Link>
            </h2>
            <p className="guide-card-desc">{guide.description}</p>
            <p className="guide-card-meta">{guide.readMinutes} min read</p>
          </li>
        ))}
      </ul>

      <p className="deal-page-back">
        <Link href="/deals">Browse all deals →</Link>
      </p>
    </main>
  );
}
