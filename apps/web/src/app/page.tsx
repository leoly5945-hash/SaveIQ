import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

import { FeaturedDeals } from "./featured-deals";
import { HomeSearch } from "./home-search";

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
        <p className="home-eyebrow">Deal finder · Canada</p>
        <h1 className="home-title">
          Stop overpaying.
          <br />
          <span>See the real price, not the list price.</span>
        </h1>
        <p className="home-sub">
          {brandName} is a hand-checked deal list for Canadian shoppers. We pick
          real products, verify the current price ourselves, and link you
          straight to the retailer. Search the list, or browse by category.
        </p>

        <HomeSearch />

        <FeaturedDeals />

        <section className="home-how" id="how-it-works">
          <div className="home-how-head">
            <h2>How SaveIQ works</h2>
            <p>
              {brandName} is a shortlist, not a store. We do the price-checking;
              you buy from the retailer you already trust.
            </p>
          </div>
          <ol className="home-how-steps">
            <li>
              <span className="home-how-num" aria-hidden="true">
                1
              </span>
              <h3>We hand-pick and price-check</h3>
              <p>
                We choose real products across everyday categories and check the
                current price on Amazon.ca ourselves. Every listing shows the
                price we found and the date we checked it.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                2
              </span>
              <h3>You search or browse</h3>
              <p>
                Type what you&apos;re after, or browse by category. No account,
                no sign-up, no fee.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                3
              </span>
              <h3>You buy from the retailer</h3>
              <p>
                Checkout happens on the retailer&apos;s own site, at the
                retailer&apos;s price. SaveIQ never adds a markup — a retailer
                affiliate commission is how we&apos;re paid.
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
