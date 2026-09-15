import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName, getSiteUrl } from "@/lib/config";

import { WatchlistView } from "./watchlist-view";

const brandName = getBrandName();

const DESCRIPTION =
  "Everything you're tracking, in one place — buy-now-or-wait for each, updated live. No account, just the email you used for alerts.";

export const metadata: Metadata = {
  title: `Your Watchlist — ${brandName}`,
  description: DESCRIPTION,
  alternates: { canonical: "/watchlist" },
  robots: { index: false, follow: true },
  openGraph: {
    title: `Your Watchlist — ${brandName}`,
    description: DESCRIPTION,
    url: `${getSiteUrl()}/watchlist`,
    type: "website",
  },
};

export default function WatchlistPage() {
  return (
    <main className="home-shell">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>Watchlist</span>
      </nav>
      <h1 className="home-title">Your Watchlist</h1>
      <p className="privacy-note">{DESCRIPTION}</p>
      <WatchlistView />
    </main>
  );
}
