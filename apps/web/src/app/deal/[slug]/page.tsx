import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  categoryPath,
  featuredDealHref,
  fetchDeal,
  formatMoney,
  formatPriceCheckedDate,
} from "@/lib/featured-deals";
import { getSiteUrl } from "@/lib/config";

export const revalidate = 3600;

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const deal = await fetchDeal(slug);
  if (!deal) {
    return { title: "Deal not found — SaveIQ" };
  }
  const price = formatMoney(deal.price_cents, deal.currency);
  const description =
    deal.blurb ??
    `${deal.title} — ${price} at ${deal.merchant}, price checked by SaveIQ.`;
  return {
    title: `${deal.title} — ${price} at ${deal.merchant} | SaveIQ`,
    description,
    alternates: { canonical: `/deal/${deal.slug}` },
    openGraph: {
      title: `${deal.title} — ${price}`,
      description,
      url: `${getSiteUrl()}/deal/${deal.slug}`,
      type: "website",
    },
  };
}

export default async function DealPage({ params }: Params) {
  const { slug } = await params;
  const deal = await fetchDeal(slug);
  if (!deal) {
    notFound();
  }

  const price = formatMoney(deal.price_cents, deal.currency);
  const checked = formatPriceCheckedDate(deal.price_checked);
  const site = getSiteUrl();

  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        name: deal.title,
        ...(deal.brand ? { brand: { "@type": "Brand", name: deal.brand } } : {}),
        ...(deal.category ? { category: deal.category } : {}),
        ...(deal.blurb ? { description: deal.blurb } : {}),
        offers: {
          "@type": "Offer",
          price: (deal.price_cents / 100).toFixed(2),
          priceCurrency: deal.currency,
          availability: "https://schema.org/InStock",
          seller: { "@type": "Organization", name: deal.merchant },
          url: `${site}/deal/${deal.slug}`,
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Deals", item: `${site}/deals` },
          ...(deal.category && deal.category_slug
            ? [
                {
                  "@type": "ListItem",
                  position: 2,
                  name: deal.category,
                  item: `${site}/category/${deal.category_slug}`,
                },
              ]
            : []),
          {
            "@type": "ListItem",
            position: deal.category ? 3 : 2,
            name: deal.title,
            item: `${site}/deal/${deal.slug}`,
          },
        ],
      },
    ],
  };

  return (
    <main className="home-shell deal-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <Link href="/deals">Deals</Link>
        {deal.category && deal.category_slug ? (
          <>
            <span aria-hidden="true"> / </span>
            <Link href={categoryPath(deal.category_slug)}>{deal.category}</Link>
          </>
        ) : null}
      </nav>

      <p className="deal-page-merchant">{deal.merchant}</p>
      <h1 className="home-title deal-page-title">{deal.title}</h1>
      {deal.brand ? <p className="deal-page-brand">by {deal.brand}</p> : null}

      <p className="deal-page-price">{price}</p>
      {checked ? (
        <p className="deal-page-checked">
          Price checked {checked} — this is a snapshot, not a live price. Confirm
          the current price, delivery time and return policy at {deal.merchant}{" "}
          before you buy.
        </p>
      ) : null}

      {deal.blurb ? <p className="deal-page-blurb">{deal.blurb}</p> : null}

      <p>
        <a
          className="deal-page-cta"
          href={featuredDealHref(deal)}
          rel="sponsored noreferrer"
          target="_blank"
        >
          View deal at {deal.merchant}
        </a>
      </p>

      <p className="deal-page-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>

      <p className="deal-page-back">
        <Link href="/deals">← Browse all deals</Link>
        {deal.category && deal.category_slug ? (
          <>
            {" · "}
            <Link href={categoryPath(deal.category_slug)}>
              More {deal.category} deals
            </Link>
          </>
        ) : null}
      </p>
    </main>
  );
}
