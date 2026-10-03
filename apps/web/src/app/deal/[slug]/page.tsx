import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { safeJsonLd } from "@/lib/json-ld";

import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  categoryPath,
  dealPriceNow,
  describeVsAverage,
  featuredDealHref,
  fetchDeal,
  formatMoney,
  UNAVAILABLE_LABEL,
} from "@/lib/featured-deals";
import { ProductImage } from "@/components/product-image";
import { buyLinkRel, getSiteUrl } from "@/lib/config";

export const revalidate = 3600;

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const deal = await fetchDeal(slug);
  if (!deal) {
    return { title: "Deal not found — SaveIQ" };
  }
  const now = dealPriceNow(deal);
  const price = now.unavailableSince
    ? "currently unavailable"
    : formatMoney(now.cents, now.currency);
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

  const now = dealPriceNow(deal);
  const price = formatMoney(now.cents, now.currency);
  const checked = now.checked;
  const versus = deal.latest_price ? describeVsAverage(deal.latest_price) : null;
  const latest = deal.latest_price ?? null;
  // The Amazon product id, for the link to the full 90-day price check.
  const asin = /\/dp\/([A-Z0-9]{10})(?:[/?]|$)/.exec(deal.product_url ?? "")?.[1] ?? null;
  const site = getSiteUrl();

  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        // No `offers` here on purpose — see check/[asin]/page.tsx for why:
        // an Offer with a price makes Google validate this as a Merchant
        // Listing, which needs real shippingDetails/hasMerchantReturnPolicy
        // that belong to the actual seller, not to us.
        "@type": "Product",
        name: deal.title,
        ...(deal.brand ? { brand: { "@type": "Brand", name: deal.brand } } : {}),
        ...(deal.category ? { category: deal.category } : {}),
        ...(deal.blurb ? { description: deal.blurb } : {}),
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
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
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

      <div className="pp-top pp-top-deal">
        <div className="pp-media">
          <ProductImage
            categorySlug={deal.category_slug}
            href={now.unavailableSince ? null : featuredDealHref(deal)}
            size="page"
            src={deal.image_url}
            title={deal.title}
          />
        </div>
        <div className="pp-summary">
          <p className="deal-page-merchant">{deal.merchant}</p>
          <h1 className="home-title deal-page-title">{deal.title}</h1>
          {deal.brand ? <p className="deal-page-brand">by {deal.brand}</p> : null}

          {now.unavailableSince ? (
            <>
              <p className="deal-page-unavailable">{UNAVAILABLE_LABEL}</p>
              <p className="deal-page-checked">
                Our daily price check on {now.unavailableSince} found no seller
                offering it on Amazon.ca, so we are not showing a price or a buy
                link. We keep checking every morning and the price comes back
                here as soon as it is on sale again.
                {now.checked
                  ? ` The last price we checked was ${price} (${now.checked}).`
                  : null}
              </p>
            </>
          ) : null}
          {!now.unavailableSince ? <p className="deal-page-price">{price}</p> : null}
          {versus && !now.unavailableSince ? (
            <p className="price-drop-versus">{versus}</p>
          ) : null}

          {!now.unavailableSince ? (
            <p className="pp-actions">
              <a
                className="deal-page-cta"
                href={featuredDealHref(deal)}
                rel={buyLinkRel(featuredDealHref(deal))}
                target="_blank"
              >
                View deal at {deal.merchant}
              </a>
              {asin ? (
                <Link className="pp-secondary" href={`/check/${asin}`}>
                  See 90-day price history
                </Link>
              ) : null}
            </p>
          ) : null}

          {checked && !now.unavailableSince ? (
            <p className="deal-page-checked">
              {now.daily
                ? `Recorded ${checked} by our daily price check`
                : `Price checked ${checked}`}{" "}
              — this is a snapshot, not a live price. Confirm the current price,
              delivery time and return policy at {deal.merchant} before you buy.
            </p>
          ) : null}
        </div>
      </div>

      {latest && !now.unavailableSince ? (
        <dl className="pp-stats pp-stats-row">
          <div className="pp-stats-now pp-stats-neutral">
            <dt>Recorded price</dt>
            <dd>{formatMoney(latest.price_cents, latest.currency)}</dd>
          </div>
          {latest.avg90_cents ? (
            <div>
              <dt>90-day average</dt>
              <dd>{formatMoney(latest.avg90_cents, latest.currency)}</dd>
            </div>
          ) : null}
          {typeof latest.pct_below_avg90 === "number" && latest.pct_below_avg90 !== 0 ? (
            <div>
              <dt>Compared with the average</dt>
              <dd>
                {latest.pct_below_avg90 > 0
                  ? `${latest.pct_below_avg90}% below`
                  : `${-latest.pct_below_avg90}% above`}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {deal.blurb ? <p className="deal-page-blurb">{deal.blurb}</p> : null}

      <p className="deal-page-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>

      <p className="deal-page-back">
        <Link href="/deals">← See every price check</Link>
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
