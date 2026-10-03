import Link from "next/link";

import { getBrandName } from "@/lib/config";

import { MapleLeaf } from "./product-art";

// Shared site header: logo with the tagline, and the main navigation. Rendered
// from the root layout so every page — not just the homepage — can reach the
// price check, Price Watch and the guides.
export function SiteHeader() {
  const brandName = getBrandName();

  return (
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
          <Link href="/#price-check">Price Check</Link>
          <Link href="/amazon-price-history">Price History</Link>
          <Link href="/deals">Price Watch</Link>
          <Link href="/guides">Buying Guides</Link>
          <Link href="/watchlist">Price Alerts</Link>
          <Link href="/extension">Extension</Link>
          <Link href="/about">About</Link>
        </nav>
      </div>
    </header>
  );
}
