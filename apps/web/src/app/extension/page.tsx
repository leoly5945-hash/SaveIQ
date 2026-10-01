import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName } from "@/lib/config";
import { fetchCheckByAsin, formatMoney, VERDICT_COPY } from "@/lib/price-check";

// The preview card shows today's real verdict for one product, so re-render hourly.
export const revalidate = 3600;

const STORE_URL =
  "https://chromewebstore.google.com/detail/epcfmakpbfdeonhppndolmadnbakjoie";
// Dell 27" 4K monitor — a product with a full 90-day history.
const PREVIEW_ASIN = "B0F1GF1KFC";
// Same wording as the extension's own card (apps/extension/content.js).
const CARD_LABEL = {
  BUY: "Buy now",
  WAIT: "Wait",
  FAIR: "Fair price",
  UNKNOWN: "Not enough data",
} as const;

export function generateMetadata(): Metadata {
  const brand = getBrandName();
  return {
    title: `${brand} browser extension — buy now or wait, on the Amazon.ca page`,
    description: `The free ${brand} extension for Chrome shows a buy-now-or-wait verdict from 90 days of price history right on any Amazon.ca product page.`,
    alternates: { canonical: "/extension" },
  };
}

export default async function ExtensionPage() {
  const brand = getBrandName();
  const preview = await fetchCheckByAsin(PREVIEW_ASIN);
  const verdict = preview?.assessment.verdict ?? "FAIR";
  const tone = VERDICT_COPY[verdict].tone;

  return (
    <main className="home-shell privacy-page">
      <p className="crumbs">
        <Link href="/">{brand}</Link> <span aria-hidden="true">/</span> Browser
        extension
      </p>

      <h1>The {brand} extension</h1>
      <p>
        Our free browser extension puts the {brand} verdict on the Amazon.ca
        product page itself, so you don&apos;t have to copy a link and come
        back here.
      </p>

      <div className="ext-layout">
        <section className="privacy-section ext-main">
          <h2>{brand} for Google Chrome</h2>
          <p>Free. No account, no sign-in.</p>
          <p>
            <a
              className="ext-cta"
              href={STORE_URL}
              rel="noreferrer"
              target="_blank"
            >
              Add to Chrome — Chrome Web Store
            </a>
          </p>

          <h3>Features</h3>
          <ul>
            <li>
              A buy-now, fair-price or wait verdict on every Amazon.ca product
              page, with no click needed.
            </li>
            <li>
              Today&apos;s price next to the one-line reason, from 90 days of
              price history.
            </li>
            <li>
              A cheaper price at another Canadian store, when we can match the
              same product.
            </li>
            <li>
              One click through to the full {brand} check: the 90-day range,
              whether the discount is real, and a price-drop alert.
            </li>
          </ul>

          <h3>Other browsers</h3>
          <ul>
            <li>
              <strong>Microsoft Edge and Brave</strong> install extensions from
              the Chrome Web Store, so the same button works.
            </li>
            <li>
              <strong>Firefox and Safari</strong>: there is no extension yet.
              Use the <Link href="/tools">one-click bookmarklet</Link> instead.
            </li>
          </ul>

          <h3>What it sends</h3>
          <p>
            The product ID of the Amazon.ca page you are viewing, so we can look
            up its price history. That is the same request this site makes when
            you paste a link. It runs on Amazon.ca only, and does not read your
            Amazon account, your orders or your browsing on other sites. See the{" "}
            <Link href="/privacy">privacy policy</Link>.
          </p>
        </section>

        <aside className="ext-preview" aria-label="Preview of the extension card">
          <h2>What it looks like</h2>
          <div className="ext-browser">
            <div className="ext-browser-bar">
              <span className="ext-dot" />
              <span className="ext-dot" />
              <span className="ext-dot" />
              <span className="ext-url">amazon.ca/dp/{PREVIEW_ASIN}</span>
            </div>
            <div className="ext-page">
              <div className="ext-ph ext-ph-img" />
              <div className="ext-ph-col">
                <div className="ext-ph ext-ph-line" />
                <div className="ext-ph ext-ph-line ext-ph-short" />
                <div className="ext-ph ext-ph-line ext-ph-price" />
              </div>
              <div className={`ext-card ext-card-${tone}`}>
                <p className="ext-card-brand">{brand}</p>
                <p className="ext-card-verdict">{CARD_LABEL[verdict]}</p>
                {preview ? (
                  <>
                    <p className="ext-card-price">
                      {formatMoney(
                        preview.assessment.effective_price.effective_cents,
                        preview.assessment.effective_price.currency
                      )}
                    </p>
                    <p className="ext-card-reason">
                      {preview.explanation?.headline ?? VERDICT_COPY[verdict].blurb}
                    </p>
                  </>
                ) : (
                  <p className="ext-card-reason">{VERDICT_COPY[verdict].blurb}</p>
                )}
                <p className="ext-card-link">See full comparison →</p>
              </div>
            </div>
          </div>
          <p className="ext-caption">
            {preview ? (
              <>
                A drawing of the card, filled with today&apos;s real verdict for{" "}
                <Link href={`/check/${PREVIEW_ASIN}`}>
                  {preview.title ?? "this product"}
                </Link>
                . It sits in the bottom-right corner of the Amazon.ca page.
              </>
            ) : (
              <>
                A drawing of the card. It sits in the bottom-right corner of the
                Amazon.ca page.
              </>
            )}
          </p>
        </aside>
      </div>
    </main>
  );
}
