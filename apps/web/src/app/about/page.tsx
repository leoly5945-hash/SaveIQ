import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName, getSiteUrl } from "@/lib/config";

const brandName = getBrandName();

const OPERATOR_NAME = "Nextwave Software Company";
const CONTACT_NAME = "Leo Do";
const CONTACT_EMAIL = "leoly5945@gmail.com";

const DESCRIPTION =
  "Who runs SaveIQ, how it makes money, and the rules we hold ourselves to when we list a price.";

export const metadata: Metadata = {
  title: `About ${brandName}`,
  description: DESCRIPTION,
  alternates: { canonical: "/about" },
  openGraph: {
    title: `About ${brandName}`,
    description: DESCRIPTION,
    url: `${getSiteUrl()}/about`,
    type: "website",
  },
};

export default function AboutPage() {
  const site = getSiteUrl();
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        name: brandName,
        url: site,
        description:
          "A comparison and deal-discovery site for Canadian shoppers, operated by " +
          `${OPERATOR_NAME}.`,
        email: CONTACT_EMAIL,
        founder: { "@type": "Person", name: CONTACT_NAME },
        parentOrganization: { "@type": "Organization", name: OPERATOR_NAME },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "SaveIQ", item: `${site}/` },
          { "@type": "ListItem", position: 2, name: "About", item: `${site}/about` },
        ],
      },
    ],
  };

  return (
    <main className="home-shell privacy-page about-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>About</span>
      </nav>

      <h1 className="home-title">About {brandName}</h1>
      <p className="privacy-note">{DESCRIPTION}</p>

      <section className="privacy-section">
        <h2>What SaveIQ is</h2>
        <p>
          {brandName} ({site.replace(/^https?:\/\//, "")}) is a comparison and
          deal-discovery site for shoppers in Canada. We hand-pick real products,
          check their current price ourselves, and link out to the retailer so
          you can buy from a name you already know. There is an AI-assisted
          search that reads what you type and finds matching products in our
          catalogue.
        </p>
        <p>
          SaveIQ is not a store. We do not hold inventory, take payment, or ship
          anything. Every purchase happens on the retailer&apos;s own site under
          the retailer&apos;s own terms.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Who runs it</h2>
        <p>
          {brandName} is operated by <strong>{OPERATOR_NAME}</strong>, a company
          registered in Vietnam, from Vancouver, BC, Canada. The person
          responsible for the site is {CONTACT_NAME}. You can reach us at{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </section>

      <section className="privacy-section">
        <h2>How SaveIQ makes money</h2>
        <p>
          When you follow a link from SaveIQ to a retailer and buy something, the
          retailer&apos;s affiliate programme pays us a commission. That
          commission comes out of the retailer&apos;s margin, not your price —
          you pay the same as you would going to the retailer directly. We take
          no fee from shoppers and we never add a markup.
        </p>
        <p>
          As an Amazon Associate, SaveIQ earns from qualifying purchases. Where
          we link to other retailers, the same applies through their programmes.
        </p>
      </section>

      <section className="privacy-section">
        <h2>The rules we hold ourselves to</h2>
        <ul>
          <li>
            Every price we show is a real price we checked by hand, with the date
            we checked it. It is a snapshot, not a live figure — always confirm
            the current price at the retailer before you buy.
          </li>
          <li>
            No invented &ldquo;was&rdquo; prices, no fake discount percentages, no
            &ldquo;lowest in 60 days&rdquo; claims, and no countdown timers or
            fake stock scarcity.
          </li>
          <li>
            We tell you to read the retailer&apos;s own terms — their price,
            payment, delivery time, and return and refund policy — because those
            are set by the retailer, not by us.
          </li>
          <li>
            No account, no login, no third-party advertising trackers. See our{" "}
            <Link href="/privacy">Privacy Policy</Link> for what little we do
            store.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>Where to start</h2>
        <p>
          Browse the <Link href="/deals">current deals</Link>, or read the{" "}
          <Link href="/guides">buying guides</Link> for how to tell a real price
          from a marked-up one. The full <Link href="/terms">Terms of Use</Link>{" "}
          cover the legal side.
        </p>
      </section>
    </main>
  );
}
