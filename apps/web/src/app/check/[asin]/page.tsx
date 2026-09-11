import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchAcquireByAsin } from "@/lib/acquire";
import { fetchAlternativesByAsin } from "@/lib/alternatives";
import { getBrandName, getSiteUrl } from "@/lib/config";
import {
  fetchCheckByAsin,
  formatMoney,
  ninetyDayBand,
  VERDICT_COPY,
} from "@/lib/price-check";

import { AcquireBlock } from "../../acquire-block";
import { AlternativesBlock } from "../../alternatives-block";
import { BuyCta } from "../../buy-cta";
import { ComparisonBlock } from "../../comparison";
import { OfferSpread } from "../../offer-spread";
import { Sparkline } from "../../sparkline";

export const revalidate = 3600;

type Params = { params: Promise<{ asin: string }> };

const ASIN_RE = /^[A-Za-z0-9]{10}$/;

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { asin } = await params;
  if (!ASIN_RE.test(asin)) {
    return { title: `Price check — ${getBrandName()}` };
  }
  const result = await fetchCheckByAsin(asin);
  const brand = getBrandName();
  if (!result) {
    return { title: `Price check — ${brand}`, robots: { index: false } };
  }
  const name = result.title ?? `ASIN ${asin.toUpperCase()}`;
  const v = VERDICT_COPY[result.assessment.verdict];
  const price = formatMoney(
    result.assessment.effective_price.effective_cents,
    result.assessment.effective_price.currency
  );
  const description = `${brand} price check for ${name}: ${v.label} at ${price}. ${v.blurb}`;
  return {
    title: `${name} — ${v.label} at ${price} | ${brand}`,
    description,
    alternates: { canonical: `/check/${asin.toUpperCase()}` },
    openGraph: {
      title: `${name} — ${v.label} at ${price}`,
      description,
      url: `${getSiteUrl()}/check/${asin.toUpperCase()}`,
      type: "website",
    },
  };
}

export default async function CheckAsinPage({ params }: Params) {
  const { asin } = await params;
  if (!ASIN_RE.test(asin)) {
    notFound();
  }
  const [result, acquire] = await Promise.all([
    fetchCheckByAsin(asin),
    fetchAcquireByAsin(asin),
  ]);
  if (!result) {
    notFound();
  }
  const poorBuy =
    result.assessment.verdict === "WAIT" ||
    result.assessment.verdict === "UNKNOWN";
  const alternatives = poorBuy ? await fetchAlternativesByAsin(asin) : null;

  const brand = getBrandName();
  const { assessment } = result;
  const v = VERDICT_COPY[assessment.verdict];
  const currency = assessment.effective_price.currency;
  const effective = assessment.effective_price.effective_cents;
  const band = ninetyDayBand(assessment.intelligence);
  const name = result.title ?? `ASIN ${asin.toUpperCase()}`;

  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Product",
        name,
        offers: {
          "@type": "Offer",
          price: (effective / 100).toFixed(2),
          priceCurrency: currency,
          availability: "https://schema.org/InStock",
          url: result.product_url ?? undefined,
          seller: { "@type": "Organization", name: "Amazon.ca" },
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: brand,
            item: getSiteUrl(),
          },
          {
            "@type": "ListItem",
            position: 2,
            name: `Price check: ${name}`,
            item: `${getSiteUrl()}/check/${asin.toUpperCase()}`,
          },
        ],
      },
    ],
  };

  return (
    <main className="home-shell privacy-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <p className="crumbs">
        <Link href="/">{brand}</Link> <span aria-hidden="true">/</span> Price
        check
      </p>

      <article className={`verdict verdict-${v.tone}`}>
        <header className="verdict-head">
          <span className="verdict-badge">{v.label}</span>
          <div className="verdict-headline">
            <h1 className="verdict-title">{name}</h1>
            <p className="verdict-blurb">{v.blurb}</p>
          </div>
        </header>

        {result.narration ? (
          <p className="verdict-narration">{result.narration}</p>
        ) : null}

        <div className="verdict-price">
          <span className="verdict-now">{formatMoney(effective, currency)}</span>
          <span className="verdict-conf">confidence: {assessment.confidence}</span>
        </div>

        {result.buy_url ?? result.product_url ? (
          <BuyCta
            amazonHref={result.buy_url ?? result.product_url ?? ""}
            amazonPriceCents={effective}
            cheapest={result.comparison?.cheapest ?? null}
            currency={currency}
            top
          />
        ) : null}

        {result.sparkline.length >= 2 ? (
          <div className="verdict-spark">
            <Sparkline points={result.sparkline} tone={v.tone} />
            <div className="verdict-spark-scale">
              <span>{formatMoney(band.min, currency)}</span>
              <span>90 days</span>
              <span>{formatMoney(band.max, currency)}</span>
            </div>
          </div>
        ) : band.min !== null && band.max !== null ? (
          <p className="verdict-band">
            90-day range {formatMoney(band.min, currency)} –{" "}
            {formatMoney(band.max, currency)}
            {band.avg !== null ? (
              <> · avg {formatMoney(band.avg, currency)}</>
            ) : null}
          </p>
        ) : null}

        {assessment.reasons.length > 0 ? (
          <ul className="verdict-reasons">
            {assessment.reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        ) : null}

        <OfferSpread spread={result.spread} />

        <ComparisonBlock comparison={result.comparison} />

        <AcquireBlock data={acquire} />

        <AlternativesBlock data={alternatives} />

        {result.buy_url ?? result.product_url ? (
          <BuyCta
            amazonHref={result.buy_url ?? result.product_url ?? ""}
            amazonPriceCents={effective}
            cheapest={result.comparison?.cheapest ?? null}
            currency={currency}
          />
        ) : null}

        <p className="verdict-fineprint">
          Price checked just now from public price-history data. Confirm at the
          retailer before you buy. {brand} may earn an affiliate commission if
          you buy through a link — that never changes the verdict, or which
          retailer we point you to.
        </p>
      </article>

      <p className="privacy-section">
        Want to check a different product?{" "}
        <Link href="/">Paste any Amazon.ca link on the homepage</Link>, or set a
        price-drop alert.
      </p>
    </main>
  );
}
