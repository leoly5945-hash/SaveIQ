import Link from "next/link";
import type { Metadata } from "next";

import { getSiteUrl } from "@/lib/config";
import { GUIDES, guidePath } from "@/lib/guides";

import { ProductArt } from "@/components/product-art";

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

function formatGuideDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-CA", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  });
}

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
        {GUIDES.filter((guide) => !guide.unlisted).map((guide) => (
          <li className="hp-guide-card" key={guide.slug}>
            <ProductArt categorySlug="guide" size="tile" title={guide.title} />
            <div>
              <p className="hp-guide-tag">Guide</p>
              <h2 className="guide-card-title">
                <Link href={guidePath(guide.slug)}>{guide.title}</Link>
              </h2>
              <p className="guide-card-desc">{guide.description}</p>
              <p className="guide-card-meta">
                Updated {formatGuideDate(guide.updated)} · {guide.readMinutes}{" "}
                min read
              </p>
            </div>
          </li>
        ))}
      </ul>

      <p className="deal-page-back">
        <Link href="/deals">See recent price checks →</Link>
      </p>
    </main>
  );
}
