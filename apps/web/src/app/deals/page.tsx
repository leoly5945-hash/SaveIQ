import Link from "next/link";
import type { Metadata } from "next";

import { DealGrid } from "@/components/deal-card";
import { PriceDropGrid } from "@/components/price-drops";
import { getSiteUrl } from "@/lib/config";
import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  FEATURED_DEALS_BLURB,
  categoryPath,
  fetchDealCategories,
  fetchDeals,
  fetchPriceDrops,
  PRICE_DROPS_BLURB,
  PRICE_DROPS_EMPTY,
  PRICE_DROPS_HEADING,
} from "@/lib/featured-deals";

// Always render fresh so the catalogue is never served empty to a crawler.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Price Watch — everyday prices re-checked daily in Canada | SaveIQ",
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
  const [deals, categories, drops] = await Promise.all([
    fetchDeals(),
    fetchDealCategories(),
    fetchPriceDrops(12),
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

      <section className="price-drops" aria-labelledby="price-drops-heading">
        <h2 id="price-drops-heading" className="price-drops-heading">
          {PRICE_DROPS_HEADING}
        </h2>
        <p className="deals-page-intro">{PRICE_DROPS_BLURB}</p>
        {drops.length > 0 ? (
          <PriceDropGrid deals={drops} />
        ) : (
          <p className="state-message">{PRICE_DROPS_EMPTY}</p>
        )}
      </section>

      <h2 className="price-drops-heading">All price checks</h2>

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
