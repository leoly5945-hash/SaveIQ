import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

import { HomeSearch } from "./home-search";
import { HotDeals } from "./hot-deals";

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
        <HotDeals />

        <footer className="home-footer">
          <div className="home-footer-org">
            <p className="home-footer-brand">{brandName}</p>
            <p>
              Operated by <strong>Nextwave Software Company</strong>
              <br />
              4641 Dunbar St, Vancouver, BC, Canada
            </p>
            <p className="home-footer-links">
              <a href="mailto:info@saveiq.ca">info@saveiq.ca</a>
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
