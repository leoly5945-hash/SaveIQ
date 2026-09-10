import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

import { CheckBox } from "./check-box";
import { DiscoverBox } from "./discover-box";
import { FeaturedDeals } from "./featured-deals";

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
            <Link href="/deals">Deals</Link>
            <Link href="/guides">Guides</Link>
            <Link href="/about">About</Link>
            <a href="#how-it-works">How it works</a>
          </nav>
        </div>
        <p className="home-valueprop">
          <span className="home-valueprop-dot" aria-hidden="true" />
          No fees. No account. No markup.
        </p>
      </header>

      <main className="home-shell">
        <p className="home-eyebrow">Price check · Canada</p>
        <h1 className="home-title">
          Paste an Amazon.ca link.
          <br />
          <span>We&apos;ll tell you: buy, or wait.</span>
        </h1>
        <p className="home-sub">
          {brandName} reads the last 90 days of price history and gives you one
          clear call — with the reasons. Not a good time? Leave your email and
          we&apos;ll ping you once when it drops.
        </p>

        <CheckBox />

        <DiscoverBox />

        <p className="home-bookmarklet-hint">
          Check straight from the Amazon page instead —{" "}
          <Link href="/tools">add the 1-click bookmarklet</Link>.
        </p>

        <FeaturedDeals />

        <section className="home-how" id="how-it-works">
          <div className="home-how-head">
            <h2>How the check works</h2>
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
              <h3>You paste a link</h3>
              <p>
                Any Amazon.ca product page. We pull its price history — the
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
        </section>

        <footer className="home-footer">
          <div className="home-footer-org">
            <p className="home-footer-brand">{brandName}</p>
            <p>
              <strong>Nextwave Software Company</strong> (registered in Vietnam)
              {" · "}Vancouver, BC, Canada
              <br />
              Contact: Leo Do —{" "}
              <a href="mailto:leoly5945@gmail.com">leoly5945@gmail.com</a>
            </p>
            <p className="home-footer-links">
              <Link href="/deals">Deals</Link>
              <span aria-hidden="true"> · </span>
              <Link href="/guides">Guides</Link>
              <span aria-hidden="true"> · </span>
              <Link href="/tools">Bookmarklet</Link>
              <span aria-hidden="true"> · </span>
              <Link href="/about">About</Link>
              <span aria-hidden="true"> · </span>
              <Link href="/privacy">Privacy</Link>
              <span aria-hidden="true"> · </span>
              <Link href="/terms">Terms</Link>
            </p>
          </div>
          <p>{HOME_AFFILIATE_DISCLOSURE}</p>
          <p className="home-footer-legal">
            © 2026 Nextwave Software Company. All rights reserved.
          </p>
        </footer>
      </main>
    </div>
  );
}
