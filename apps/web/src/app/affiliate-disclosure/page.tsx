import Link from "next/link";
import type { Metadata } from "next";

import { CONTACT_EMAIL, getBrandName, getSiteUrl } from "@/lib/config";
import { AMAZON_ASSOCIATE_DISCLOSURE } from "@/lib/featured-deals";
import { safeJsonLd } from "@/lib/json-ld";

const brandName = getBrandName();

const LAST_UPDATED = "September 18, 2026";

const DESCRIPTION =
  "How SaveIQ earns money from affiliate links, and what that does and does not affect.";

export const metadata: Metadata = {
  title: `Affiliate & Advertising Disclosure | ${brandName}`,
  description: DESCRIPTION,
  alternates: { canonical: "/affiliate-disclosure" },
  openGraph: {
    title: `${brandName} Affiliate & Advertising Disclosure`,
    description: DESCRIPTION,
    url: `${getSiteUrl()}/affiliate-disclosure`,
    type: "website",
  },
};

export default function AffiliateDisclosurePage() {
  const site = getSiteUrl();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: brandName, item: `${site}/` },
      {
        "@type": "ListItem",
        position: 2,
        name: "Affiliate Disclosure",
        item: `${site}/affiliate-disclosure`,
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
        <span>Affiliate Disclosure</span>
      </nav>

      <h1 className="home-title">Affiliate &amp; Advertising Disclosure</h1>
      <p className="privacy-note">{DESCRIPTION}</p>
      <p className="privacy-note">Last updated: {LAST_UPDATED}</p>

      <section className="privacy-section">
        <h2>The short version</h2>
        <p>
          Some links on {brandName} are affiliate links. If you buy through one,
          the retailer may pay us a commission. It costs you nothing extra, and
          it does not change what we tell you.
        </p>
      </section>

      <section className="privacy-section">
        <h2>How we earn money</h2>
        <p>
          {brandName} is free to use and has no accounts, subscriptions or
          markup. We are paid through retailers&apos; affiliate programmes:
        </p>
        <ul>
          <li>{AMAZON_ASSOCIATE_DISCLOSURE}</li>
          <li>
            We take part in the eBay Partner Network and may earn a commission
            on qualifying eBay purchases.
          </li>
          <li>
            Where we link to other retailers, the same applies through their
            affiliate programmes, which are sometimes run by an affiliate
            network on the retailer&apos;s behalf.
          </li>
        </ul>
        <p>
          The commission comes out of the retailer&apos;s margin, not your
          price. You pay the same as you would going to the retailer directly.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Financial products and risk warning</h2>
        <p>
          Some pages compare financial products such as crypto trading
          platforms, credit cards or brokerages. If you sign up through a link
          on one of them, we may earn a commission. That does not change what we
          publish, and we only feature crypto platforms that are authorized to
          serve Canadians.
        </p>
        <p>
          Content on {brandName} is general information, not financial,
          investment, tax or legal advice, and we do not recommend that you buy,
          sell or hold any asset. Crypto assets are volatile, and you can lose
          some or all of the money you put in. Only use a platform that is
          authorized in Canada, and only risk money you can afford to lose.
        </p>
      </section>

      <section className="privacy-section">
        <h2>What this does not affect</h2>
        <ul>
          <li>
            Our Buy / Wait / Fair verdicts are calculated from price and price
            history. Commission rates are not an input.
          </li>
          <li>
            No retailer, brand or network can pay for a better verdict, a higher
            position or a favourable guide.
          </li>
          <li>
            We may recommend waiting, or not buying at all, even though that
            earns us nothing.
          </li>
        </ul>
        <p>
          Our approach to research and independence is set out in the{" "}
          <Link href="/editorial-guidelines">Editorial Guidelines</Link>.
        </p>
      </section>

      <section className="privacy-section">
        <h2>How affiliate links work here</h2>
        <p>
          Links from {brandName} to a retailer can be affiliate links. We say so
          near the links where they appear and on this page. When you click one,
          the click is logged on our own server so we can match commissions to
          the right link, and the retailer or its network may set its own
          cookies. See our <Link href="/privacy">Privacy Policy</Link> for what
          we store.
        </p>
        <p>
          You are always free to buy directly from the retailer without using
          our links.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Why we publish this</h2>
        <p>
          We want the commercial relationship behind this site to be plain to
          anyone reading it, in line with Canadian guidance on clearly
          disclosing material connections. Questions? Email{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </section>
    </main>
  );
}
