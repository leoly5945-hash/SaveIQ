import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

const CONTACT_NAME = "Leo Do";
const CONTACT_EMAIL = "leoly5945@gmail.com";
const OPERATOR_NAME = "Nextwave Software Company";
const LAST_UPDATED = "August 28, 2026";

export const metadata: Metadata = {
  title: `Terms of Use — ${brandName}`,
  description: "The terms for using SaveIQ.",
};

export default function TermsPage() {
  return (
    <main className="home-shell privacy-page">
      <p>
        <Link href="/">Back to {brandName}</Link>
        {" · "}
        <Link href="/privacy">Privacy</Link>
      </p>
      <h1 className="home-title">Terms of Use</h1>
      <p className="privacy-note">Last updated: {LAST_UPDATED}</p>

      <section className="privacy-section">
        <h2>About these terms</h2>
        <p>
          {brandName} ({`https://saveiq.ca`}) is operated by {OPERATOR_NAME}
          {" "}(4641 Dunbar St, Vancouver, BC, Canada). By using the site you
          agree to these terms. If you do not agree, please do not use the site.
        </p>
      </section>

      <section className="legal-callout">
        <p>
          <strong>
            Before you buy, check the details on the retailer&apos;s own
            website:
          </strong>{" "}
          the current price, the payment terms, the estimated delivery time,
          and the return and refund policy. Those are all set and handled by
          the retailer — {brandName} only points you to the offer and is not
          part of the sale.
        </p>
      </section>

      <section className="privacy-section">
        <h2>What {brandName} does</h2>
        <p>
          {brandName} is a free tool that helps you discover product deals and
          affiliate offers from retailers in Canada. It is free to use — there
          are no fees, no account, and no sign-up — and we do not collect
          personal information through the site (see our{" "}
          <Link href="/privacy">Privacy Policy</Link>).
        </p>
      </section>

      <section className="privacy-section">
        <h2>Prices and offers come from third parties</h2>
        <p>
          Prices, discounts, coupons, availability, and product details are
          gathered from retailers and affiliate networks and can change, sell
          out, or be out of date at any time. Always confirm the current price,
          taxes, shipping cost, and delivery estimate on the retailer&apos;s own
          website before you buy. {brandName} does not guarantee any price,
          saving, delivery time, or that an offer is still available.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Buying from a retailer</h2>
        <p>
          {brandName} is not a store and does not sell anything. When you follow
          an outbound link and make a purchase, that purchase is solely between
          you and the retailer. The retailer&apos;s own terms — which you should
          read before ordering — govern payment, shipping and delivery times,
          warranties, returns, refunds, and customer support. Please direct any
          order, product, payment, delivery, or return issue to the retailer,
          not to {brandName}.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Affiliate links</h2>
        <p>
          Some outbound links are affiliate links. If you buy through them,
          {" "}{brandName} may earn a commission from the retailer or network, at
          no extra cost to you. This never changes the price you pay.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Acceptable use</h2>
        <p>
          Use the site for your own personal, non-commercial deal research. Do
          not scrape, copy, or bulk-download the site or its data, do not use
          automated tools beyond normal browsing, and do not attempt to disrupt
          the site or gain unauthorized access to it.
        </p>
      </section>

      <section className="privacy-section">
        <h2>No warranty and limitation of liability</h2>
        <p>
          The site is provided &quot;as is&quot;, without warranties of any
          kind. To the extent permitted by law, {OPERATOR_NAME} is not liable
          for any loss or damage arising from your use of the site or from any
          purchase you make from a retailer.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Changes</h2>
        <p>
          We may update the site or these terms as the product changes. We&apos;ll
          update the &quot;Last updated&quot; date above when we do, and
          continued use after a change means you accept the updated terms.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Governing law</h2>
        <p>
          These terms are governed by the laws of the Province of British
          Columbia and the federal laws of Canada that apply there.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Contact</h2>
        <p>
          Questions about these terms: {CONTACT_NAME},{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </section>
    </main>
  );
}
