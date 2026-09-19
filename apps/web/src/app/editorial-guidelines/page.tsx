import Link from "next/link";
import type { Metadata } from "next";

import { CONTACT_EMAIL, getBrandName, getSiteUrl } from "@/lib/config";
import { safeJsonLd } from "@/lib/json-ld";

const brandName = getBrandName();

const OPERATOR_NAME = "Nextwave Software Company";
const CONTACT_NAME = "Leo Do";
const LAST_UPDATED = "September 18, 2026";

const DESCRIPTION =
  "How SaveIQ researches products, checks prices and writes its guides — and the rules that keep them independent.";

export const metadata: Metadata = {
  title: `Editorial Guidelines | ${brandName}`,
  description: DESCRIPTION,
  alternates: { canonical: "/editorial-guidelines" },
  openGraph: {
    title: `${brandName} Editorial Guidelines`,
    description: DESCRIPTION,
    url: `${getSiteUrl()}/editorial-guidelines`,
    type: "website",
  },
};

export default function EditorialGuidelinesPage() {
  const site = getSiteUrl();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: brandName, item: `${site}/` },
      {
        "@type": "ListItem",
        position: 2,
        name: "Editorial Guidelines",
        item: `${site}/editorial-guidelines`,
      },
    ],
  };

  return (
    <main className="home-shell privacy-page about-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
      />

      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">{brandName}</Link>
        <span aria-hidden="true"> / </span>
        <span>Editorial Guidelines</span>
      </nav>

      <h1 className="home-title">Editorial Guidelines</h1>
      <p className="privacy-note">{DESCRIPTION}</p>
      <p className="privacy-note">Last updated: {LAST_UPDATED}</p>

      <section className="privacy-section">
        <h2>What we publish</h2>
        <p>
          {brandName} publishes buying guides, comparisons and price-history
          analysis to help shoppers in Canada decide whether, what and when to
          buy. Our job is to explain the trade-offs clearly, not to push a
          purchase.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Independence</h2>
        <ul>
          <li>
            Retailers, brands and affiliate networks do not pay for placement,
            rankings or verdicts, and they do not review or edit our content
            before it is published.
          </li>
          <li>
            Our Buy / Wait / Fair verdicts come from a fixed set of rules that
            use price and price history as inputs. Commission rates are not an
            input, so a higher commission cannot produce a better verdict.
          </li>
          <li>
            We may earn a commission when you buy through a link on this site.
            That relationship is explained in full on our{" "}
            <Link href="/affiliate-disclosure">Affiliate Disclosure</Link>{" "}
            page.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>How we research</h2>
        <p>
          We do not lab-test products or receive products for review, and we do
          not present research as hands-on experience. Our guides and verdicts
          are built from:
        </p>
        <ul>
          <li>
            Specifications and features published by the manufacturer or the
            retailer.
          </li>
          <li>
            The price history we record at Canadian retailers, including the
            90-day high and low.
          </li>
          <li>
            Independent measurements and test results from third parties, which
            we name whenever we rely on them.
          </li>
        </ul>
        <p>
          When we are unsure of something, or a figure comes from a single
          source, we say so rather than smoothing it over.
        </p>
      </section>

      <section className="privacy-section">
        <h2>How we handle prices</h2>
        <ul>
          <li>
            A price is a snapshot from the date shown. Always confirm the
            current price at the retailer before you buy.
          </li>
          <li>
            No invented &ldquo;was&rdquo; prices, no fake discount percentages,
            no countdown timers and no fake stock scarcity.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>What we do not do</h2>
        <ul>
          <li>We do not list coupon codes, vouchers or cashback offers.</li>
          <li>
            We do not publish sponsored content presented as independent advice.
          </li>
          <li>
            We do not sell, ship or take payment for products. Every purchase
            happens on the retailer&apos;s own site under its own terms.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>Financial topics</h2>
        <ul>
          <li>
            We compare fees and terms that companies publish, and we cite the
            official page and the date we checked it.
          </li>
          <li>
            We only feature crypto platforms that appear on the Canadian
            Securities Administrators&apos; list of platforms authorized to do
            business with Canadians.
          </li>
          <li>
            We do not tell readers to buy, sell or hold any asset, and our
            content is not financial, investment, tax or legal advice. See the
            risk warning in our{" "}
            <Link href="/affiliate-disclosure">Affiliate Disclosure</Link>.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>Updates and corrections</h2>
        <p>
          Each guide shows the date it was last updated. If you find a factual
          error, email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
          and we will correct it and update the date.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Who is responsible</h2>
        <p>
          {brandName} is operated by <strong>{OPERATOR_NAME}</strong>, a company
          registered in Vietnam, from Vancouver, BC, Canada. The person
          responsible for the site is {CONTACT_NAME}. Read more on the{" "}
          <Link href="/about">About</Link> page.
        </p>
      </section>
    </main>
  );
}
