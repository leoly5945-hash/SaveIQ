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
            <a href="#how-it-works">How it works</a>
            <Link href="/privacy">Privacy</Link>
          </nav>
        </div>
        <p className="home-valueprop">
          <span className="home-valueprop-dot" aria-hidden="true" />
          No fees. No account. No markup — just the lowest verified price.
        </p>
      </header>

      <main className="home-shell">
        <p className="home-eyebrow">AI deal finder · Canada</p>
        <h1 className="home-title">
          Stop overpaying.
          <br />
          <span>Know the real lowest price.</span>
        </h1>
        <p className="home-sub">
          Tell {brandName} what you want. It scans retailers, stacks coupons and
          cashback, and ranks the true bottom-line price.
        </p>

        <HomeSearch />

        <FeaturedDeals />

        <section className="home-how" id="how-it-works">
          <div className="home-how-head">
            <h2>How SaveIQ works</h2>
            <p>
              SaveIQ sits between you and well-known retailers. You bring the
              intent; our AI Router does the price hunting — so you buy from
              names you already trust, at the best price we can find.
            </p>
          </div>
          <ol className="home-how-steps">
            <li>
              <span className="home-how-num" aria-hidden="true">
                1
              </span>
              <h3>Tell it what you want</h3>
              <p>
                Describe the product in plain words. No account, no sign-up, no
                fee.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                2
              </span>
              <h3>The AI Router hunts</h3>
              <p>
                It reads your intent and searches trusted retailers at once,
                weighing price, coupons and cashback to find the real
                bottom-line cost.
              </p>
            </li>
            <li>
              <span className="home-how-num" aria-hidden="true">
                3
              </span>
              <h3>You buy at the best price</h3>
              <p>
                Get one ranked list and check out directly with the retailer.
                SaveIQ never adds a markup — we earn a commission from the
                retailer instead.
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
