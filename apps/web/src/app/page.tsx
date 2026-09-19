import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { GUIDES, guidePath } from "@/lib/guides";

import { CheckBox } from "./check-box";
import { DiscoverBox } from "./discover-box";
import { FeaturedDeals } from "./featured-deals";
import { MultiStoreShowcase } from "./multi-store-showcase";

const LATEST_GUIDES = [...GUIDES]
  .sort((a, b) => b.updated.localeCompare(a.updated))
  .slice(0, 3);

function formatGuideDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-CA", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  });
}

export default function Home() {
  const brandName = getBrandName();

  return (
    <div className="home-page">
      <header className="home-header">
        <div className="home-header-inner">
          <p className="home-brand">
            <span className="home-brand-mark" aria-hidden="true">
              <svg width="40" height="40" viewBox="0 0 44 44">
                <rect width="44" height="44" rx="13" fill="#ffffff" />
                <text
                  x="22"
                  y="31"
                  textAnchor="middle"
                  fontWeight="900"
                  fontSize="21"
                  letterSpacing="-1"
                  fill="#0f766e"
                  style={{ fontFamily: "var(--display-font)" }}
                >
                  iQ
                </text>
                <circle cx="14.6" cy="12" r="2.6" fill="#f97316" />
              </svg>
            </span>
            {brandName}
          </p>
          <nav className="home-nav">
            <Link href="/guides">Guides</Link>
            <a href="#price-check">Price Check</a>
            <Link href="/deals">Price Watch</Link>
            <Link href="/watchlist">Watchlist</Link>
            <Link href="/about">About</Link>
            <a href="#how-we-evaluate">How we evaluate</a>
          </nav>
        </div>
        <p className="home-valueprop">
          <span className="home-valueprop-dot" aria-hidden="true" />
          No fees. No account. No markup.
        </p>
      </header>

      <main className="home-shell">
        <p className="home-eyebrow">Independent buying guides · Canada</p>
        <h1 className="home-title">
          Independent buying guides{" "}
          <br />
          <span>for Canadian shoppers.</span>
        </h1>
        <p className="home-sub">
          {brandName} publishes buying guides, side-by-side comparisons and
          price-history analysis for everyday products, and shows its reasoning.
          We don&apos;t sell products or run coupon codes or cashback programs,
          and no retailer can pay for a better verdict.
        </p>
        <div className="home-cta-row">
          <Link className="deal-card-cta" href="/guides">
            Read the buying guides
          </Link>
          <a className="home-cta-secondary" href="#price-check">
            Check a price →
          </a>
        </div>

        <section className="home-pricecheck" id="price-check" aria-labelledby="price-check-heading">
          <div className="home-how-head">
            <h2 id="price-check-heading">Check a price</h2>
            <p>
              Describe a product and {brandName} finds it, reads the last 90 days
              of price history, and gives you one clear call — with the reasons.
              Not a good time? We&apos;ll email you once when it drops.
            </p>
          </div>

          <DiscoverBox />

          <div className="home-secondary">
            <p className="home-secondary-label">
              Already looking at something on Amazon.ca? Paste the link.
            </p>
            <CheckBox />
            <p className="home-bookmarklet-hint">
              Or see the verdict right on the Amazon page —{" "}
              <a
                href="https://chromewebstore.google.com/detail/epcfmakpbfdeonhppndolmadnbakjoie"
                rel="noreferrer"
                target="_blank"
              >
                get the Chrome extension
              </a>
              , or <Link href="/tools">add the 1-click bookmarklet</Link>.
            </p>
          </div>

          <MultiStoreShowcase />
        </section>

        <section className="home-latest" aria-labelledby="latest-guides-heading">
          <div className="home-how-head">
            <h2 id="latest-guides-heading">Latest buying guides</h2>
            <p>
              Plain, factual guides written to be useful to a shopper, not to
              sell. Each one shows when it was last updated.
            </p>
          </div>
          <ul className="guides-list">
            {LATEST_GUIDES.map((guide) => (
              <li className="guide-card" key={guide.slug}>
                <h3 className="guide-card-title">
                  <Link href={guidePath(guide.slug)}>{guide.title}</Link>
                </h3>
                <p className="guide-card-desc">{guide.description}</p>
                <p className="guide-card-meta">
                  Updated {formatGuideDate(guide.updated)} · {guide.readMinutes}{" "}
                  min read
                </p>
              </li>
            ))}
          </ul>
          <p className="deal-page-back">
            <Link href="/guides">All buying guides →</Link>
          </p>
        </section>

        <section className="home-how" id="how-we-evaluate">
          <div className="home-how-head">
            <h2>How we evaluate</h2>
            <p>
              {brandName} is a read-out, not a store. We look at the numbers; you
              buy from the retailer you already trust.
            </p>
          </div>
          <ol className="home-how-steps">
            <li>
              <span className="home-how-num" aria-hidden="true">
                1
              </span>
              <h3>You describe it, or paste a link</h3>
              <p>
                Say what you want — &ldquo;robot vacuum under $600&rdquo; — or
                paste any Amazon.ca product page. We pull its price history: the
                Amazon price, the buy-box price, the 90-day high and low.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                2
              </span>
              <h3>We do the math</h3>
              <p>
                A fixed set of rules compares today&apos;s price to the last 90
                days and returns <strong>Buy</strong>, <strong>Wait</strong> or{" "}
                <strong>Fair</strong> — with the reasons written out. No
                merchant pays for a better verdict; there is nowhere in the math
                to do that.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                3
              </span>
              <h3>You buy now, or wait</h3>
              <p>
                Buy through the link and checkout happens on Amazon at
                Amazon&apos;s price — a retailer affiliate commission is how
                we&apos;re paid. Waiting? Leave your email and we&apos;ll send
                one message when it drops.
              </p>
            </li>
          </ol>
          <p className="home-how-note">
            We don&apos;t lab-test products. Our guides and verdicts are built
            from published specifications, the price history we record at
            Canadian retailers, and independent measurements we cite by name.
            Read our <Link href="/editorial-guidelines">Editorial Guidelines</Link>{" "}
            and <Link href="/affiliate-disclosure">Affiliate Disclosure</Link>.
          </p>
        </section>

        <FeaturedDeals />
      </main>
    </div>
  );
}
