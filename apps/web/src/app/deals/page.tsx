import Link from "next/link";
import type { Metadata } from "next";

import { DealGrid } from "@/components/deal-card";
import { getSiteUrl } from "@/lib/config";
import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  FEATURED_DEALS_BLURB,
  categoryPath,
  fetchDealCategories,
  fetchDeals,
} from "@/lib/featured-deals";

// Always render fresh so the catalogue is never served empty to a crawler.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Price Watch — hand-checked prices in Canada | SaveIQ",
  description: FEATURED_DEALS_BLURB,
  alternates: { canonical: "/deals" },
  openGraph: {
    title: "Price Watch — SaveIQ",
    description: FEATURED_DEALS_BLURB,
    url: `${getSiteUrl()}/deals`,
    type: "website",
  },
};

export default async function DealsPage() {
  const [deals, categories] = await Promise.all([
    fetchDeals(),
    fetchDealCategories(),
  ]);

  return (
    <main className="home-shell deals-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>Price Watch</span>
      </nav>

      <h1 className="home-title deals-page-title">Price Watch</h1>
      <p className="deals-page-intro">{FEATURED_DEALS_BLURB}</p>

      {categories.length > 0 ? (
        <nav className="deals-page-cats" aria-label="Price Watch categories">
          {categories.map((cat) => (
            <Link key={cat.slug} href={categoryPath(cat.slug)}>
              {cat.name} ({cat.count})
            </Link>
          ))}
        </nav>
      ) : null}

      {deals.length > 0 ? (
        <DealGrid deals={deals} />
      ) : (
        <p className="state-message">Price checks are loading. Check back shortly.</p>
      )}

      <p className="category-page-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
    </main>
  );
}
