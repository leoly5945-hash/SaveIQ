import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { GUIDES, guidePath } from "@/lib/guides";

import { MapleLeaf, ProductArt } from "@/components/product-art";

import { CheckBox } from "./check-box";
import { DiscoverBox } from "./discover-box";
import { FeaturedDeals } from "./featured-deals";
import { HeroArt } from "./hero-art";
import { HomeCategories } from "./home-categories";
import { MultiStoreShowcase } from "./multi-store-showcase";
import { HomePriceDrops } from "./price-drops-section";

const LATEST_GUIDES = GUIDES.filter((guide) => !guide.unlisted)
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
      <header className="hp-header">
        <div className="hp-header-inner">
          <Link className="hp-brand" href="/">
            <span className="hp-brand-mark" aria-hidden="true">
              <svg width="42" height="42" viewBox="0 0 44 44">
                <rect width="44" height="44" rx="13" fill="#0f766e" />
                <text
                  x="22"
                  y="31"
                  textAnchor="middle"
                  fontWeight="900"
                  fontSize="21"
                  letterSpacing="-1"
                  fill="#ffffff"
                  style={{ fontFamily: "var(--display-font)" }}
                >
                  iQ
                </text>
                <circle cx="14.6" cy="12" r="2.6" fill="#f97316" />
              </svg>
            </span>
            <span className="hp-brand-text">
              <span className="hp-brand-name">{brandName}</span>
              <span className="hp-brand-tag">
                Smarter Shopping in Canada
                <MapleLeaf className="hp-leaf" />
              </span>
            </span>
          </Link>
          <nav className="hp-nav" aria-label="Main">
            <a href="#price-check">Price Check</a>
            <Link href="/amazon-price-history">Price History</Link>
            <Link href="/deals">Price Watch</Link>
            <Link href="/guides">Buying Guides</Link>
            <Link href="/watchlist">Price Alerts</Link>
            <Link href="/extension">Extension</Link>
            <Link href="/about">About</Link>
          </nav>
        </div>
        <div className="home-valueprop">
          <div className="home-valueprop-track" aria-hidden="true">
            <span className="home-valueprop-item">
              <span className="home-valueprop-dot" />
              No fees. No account. No markup.
            </span>
          </div>
          <p className="sr-only">No fees. No account. No markup.</p>
        </div>
      </header>

      <main className="hp-main">
        <section className="hp-hero">
          <div className="hp-hero-copy">
            <p className="home-eyebrow">Independent buying guides · Canada</p>
            <h1 className="home-title">
              Shopping intelligence{" "}
              <br />
              <span>at its smartest.</span>
            </h1>
            <p className="home-sub">
              {brandName} publishes buying guides, side-by-side comparisons and
              price-history analysis for everyday products, and shows its
              reasoning. We don&apos;t sell products or run coupon codes or
              cashback programs, and no retailer can pay for a better verdict.
            </p>
          </div>
          <div className="hp-hero-art" aria-hidden="true">
            <HeroArt />
          </div>
        </section>

        <section
          className="home-pricecheck hp-pricecheck"
          id="price-check"
          aria-labelledby="price-check-heading"
        >
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
              <Link href="/extension">get the Chrome extension</Link>
              , or <Link href="/tools">add the 1-click bookmarklet</Link>.
            </p>
          </div>

          <ul className="hp-trust">
            <li>
              <span className="hp-trust-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M9.5 14.5c.6 1 1.5 1.5 2.7 1.5 1.5 0 2.5-.8 2.5-2s-1-1.7-2.6-2.1c-1.5-.4-2.4-.9-2.4-2 0-1.1 1-1.9 2.4-1.9 1.1 0 1.9.4 2.4 1.200M12 6.500v11" />
                </svg>
              </span>
              <span>
                <strong>No fees</strong>
                Free to use, always
              </span>
            </li>
            <li>
              <span className="hp-trust-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="9" r="4" />
                  <path d="M4.5 20c1.2-3.3 4-5 7.5-5s6.3 1.7 7.5 5" />
                </svg>
              </span>
              <span>
                <strong>No account</strong>
                Nothing to sign up for
              </span>
            </li>
            <li>
              <span className="hp-trust-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M4 12.500V5.500A1.5 1.5 0 0 1 5.5 4h7l7.5 7.5-8.5 8.500z" />
                  <circle cx="8.5" cy="8.5" r="1.4" />
                </svg>
              </span>
              <span>
                <strong>No markup</strong>
                You pay the retailer&apos;s price, in CAD
              </span>
            </li>
          </ul>
        </section>

        <HomeCategories />

        <HomePriceDrops />

        <section className="home-latest" aria-labelledby="latest-guides-heading">
          <div className="hp-section-head">
            <div>
              <h2 id="latest-guides-heading">Latest buying guides</h2>
              <p>
                Plain, factual guides written to be useful to a shopper, not to
                sell. Each one shows when it was last updated.
              </p>
            </div>
            <Link className="hp-more" href="/guides">
              View all guides →
            </Link>
          </div>
          <ul className="hp-guides">
            {LATEST_GUIDES.map((guide) => (
              <li className="hp-guide-card" key={guide.slug}>
                <ProductArt categorySlug="guide" size="tile" title={guide.title} />
                <div>
                  <p className="hp-guide-tag">Guide</p>
                  <h3 className="guide-card-title">
                    <Link href={guidePath(guide.slug)}>{guide.title}</Link>
                  </h3>
                  <p className="guide-card-meta">
                    Updated {formatGuideDate(guide.updated)} · {guide.readMinutes}{" "}
                    min read
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="hp-watch" aria-label="Price Watch">
          <FeaturedDeals />

          <MultiStoreShowcase />
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
      </main>
    </div>
  );
}
