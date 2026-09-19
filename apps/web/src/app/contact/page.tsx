import Link from "next/link";
import type { Metadata } from "next";

import { CONTACT_EMAIL, getBrandName, getSiteUrl } from "@/lib/config";
import { safeJsonLd } from "@/lib/json-ld";

const brandName = getBrandName();

const OPERATOR_NAME = "Nextwave Software Company";
const CONTACT_NAME = "Leo Do";

const DESCRIPTION = `How to contact ${brandName}: corrections, questions about a guide, privacy requests and general enquiries.`;

export const metadata: Metadata = {
  title: `Contact | ${brandName}`,
  description: DESCRIPTION,
  alternates: { canonical: "/contact" },
  openGraph: {
    title: `Contact ${brandName}`,
    description: DESCRIPTION,
    url: `${getSiteUrl()}/contact`,
    type: "website",
  },
};

export default function ContactPage() {
  const site = getSiteUrl();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: brandName, item: `${site}/` },
      { "@type": "ListItem", position: 2, name: "Contact", item: `${site}/contact` },
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
        <span>Contact</span>
      </nav>

      <h1 className="home-title">Contact</h1>
      <p className="privacy-note">{DESCRIPTION}</p>

      <section className="privacy-section">
        <h2>Email</h2>
        <p>
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </p>
      </section>

      <section className="privacy-section">
        <h2>What to write to us about</h2>
        <ul>
          <li>
            <strong>A correction.</strong> If a price, specification or fee in a
            guide is wrong, tell us which page and where you saw the right
            figure. Our approach is in the{" "}
            <Link href="/editorial-guidelines">Editorial Guidelines</Link>.
          </li>
          <li>
            <strong>A question about a guide or verdict.</strong> We can explain
            how a conclusion was reached.
          </li>
          <li>
            <strong>Privacy requests.</strong> See the{" "}
            <Link href="/privacy">Privacy Policy</Link> for what we store.
          </li>
          <li>
            <strong>Anything else.</strong> Note that we do not sell placement,
            rankings or verdicts.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>What we cannot help with</h2>
        <p>
          We cannot give personal financial, investment, tax or legal advice,
          and we cannot look up or change orders, accounts or payments at a
          retailer or exchange. For those, contact the company you bought from.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Who runs {brandName}</h2>
        <p>
          {brandName} is operated by <strong>{OPERATOR_NAME}</strong>, a company
          registered in Vietnam, from Vancouver, BC, Canada. The person
          responsible for the site is {CONTACT_NAME}. More on the{" "}
          <Link href="/about">About</Link> page.
        </p>
      </section>
    </main>
  );
}
