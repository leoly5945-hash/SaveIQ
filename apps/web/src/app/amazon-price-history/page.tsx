import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName, getSiteUrl } from "@/lib/config";
import { safeJsonLd } from "@/lib/json-ld";

import { CheckBox } from "../check-box";

export const dynamic = "force-static";

const FAQ: { q: string; a: string }[] = [
  {
    q: "Does Amazon.ca show a product’s price history?",
    a: "No. A product page shows today’s price and sometimes a struck-through “List Price” or “Was Price”, but not a record of what the product sold for over time. You need a price tracker to see that.",
  },
  {
    q: "How far back does the history go?",
    a: "This page reads the last 90 days. That is enough to tell whether today’s price is low, normal or high for the product. For a chart covering several years, use Keepa or camelcamelcamel.",
  },
  {
    q: "Is it free?",
    a: "Yes. There is no account and no fee. If you buy through a link on this site we may earn an affiliate commission from the retailer, which does not change the verdict.",
  },
  {
    q: "Does it work for Amazon.com or other countries?",
    a: "No. It checks products on Amazon.ca only, with prices in Canadian dollars.",
  },
  {
    q: "Can it tell me when the price drops?",
    a: "Yes. After a check, leave your email under the result. We re-check the price once a day and send one email if it has dropped.",
  },
];

export function generateMetadata(): Metadata {
  const brand = getBrandName();
  return {
    title: `Amazon.ca price history checker and price tracker — ${brand}`,
    description:
      "Paste an Amazon.ca link to see the product’s 90-day price history, its lowest and usual price, and whether to buy now or wait. Free, no account, with price-drop alerts.",
    alternates: { canonical: "/amazon-price-history" },
  };
}

export default function AmazonPriceHistoryPage() {
  const brand = getBrandName();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    url: `${getSiteUrl()}/amazon-price-history`,
    mainEntity: FAQ.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };

  return (
    <main className="home-shell privacy-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
      />
      <p className="crumbs">
        <Link href="/">{brand}</Link> <span aria-hidden="true">/</span> Amazon.ca
        price history
      </p>

      <h1>Amazon.ca price history checker</h1>
      <p>
        Paste the link to any Amazon.ca product. You get its price history for
        the last 90 days and one clear call: buy now, or wait. Free, with no
        account.
      </p>

      <section className="home-pricecheck" aria-label="Check a price">
        <CheckBox />
      </section>

      <section className="privacy-section">
        <h2>What the check shows</h2>
        <ul>
          <li>
            The lowest, usual and highest price of the last 90 days, with
            today&apos;s price marked on that range.
          </li>
          <li>
            A verdict, Buy, Fair or Wait, and the reason for it in one line.
          </li>
          <li>
            Whether the discount is real: we compare the struck-through
            &quot;List Price&quot; with what the product has actually sold for.
          </li>
          <li>
            Other sellers on Amazon.ca, and the same product at other Canadian
            stores when we can match it.
          </li>
        </ul>
      </section>

      <section className="privacy-section">
        <h2>Track the price instead of checking again</h2>
        <p>
          If the verdict is Wait, leave your email under the result. We re-check
          the price once a day and send one email when it has dropped. Your
          tracked products are on the <Link href="/watchlist">Watchlist</Link>.
        </p>
        <p>
          The <Link href="/extension">{brand} extension for Chrome</Link> shows
          the same verdict on the Amazon.ca page itself, so you don&apos;t need
          to paste a link.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Checking a sale price</h2>
        <p>
          During sale events such as Prime Day, Black Friday and Boxing Day,
          compare the sale price with the 90-day low and the usual price, not
          with the struck-through price. A &quot;deal&quot; that is still above
          the product&apos;s usual price is not a saving.
        </p>
        <p>
          More in our guides:{" "}
          <Link href="/guide/how-to-check-amazon-ca-price-history">
            how to check Amazon.ca price history
          </Link>{" "}
          and{" "}
          <Link href="/guide/amazon-ca-price-drop-alerts">
            how to set a price-drop alert
          </Link>
          .
        </p>
      </section>

      <section className="privacy-section">
        <h2>Where the data comes from</h2>
        <p>
          Price history comes from Keepa, which records Amazon.ca prices over
          time. A product that launched a few weeks ago, or that is often out of
          stock, has too little history for a verdict, and we say so when that
          happens. Always confirm the price on Amazon.ca before you buy.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Questions</h2>
        {FAQ.map((f) => (
          <div key={f.q}>
            <h3>{f.q}</h3>
            <p>{f.a}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
