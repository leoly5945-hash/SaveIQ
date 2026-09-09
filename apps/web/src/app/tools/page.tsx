import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName, getSiteUrl } from "@/lib/config";

import { BookmarkletLink } from "../bookmarklet-link";

export const dynamic = "force-static";

export function generateMetadata(): Metadata {
  const brand = getBrandName();
  return {
    title: `The 1-click bookmarklet — ${brand}`,
    description: `Check any Amazon.ca price from the product page itself, without copying the link.`,
    alternates: { canonical: "/tools" },
  };
}

export default function ToolsPage() {
  const brand = getBrandName();
  const site = getSiteUrl();

  return (
    <main className="home-shell privacy-page">
      <p className="crumbs">
        <Link href="/">{brand}</Link> <span aria-hidden="true">/</span> Bookmarklet
      </p>

      <h1>Check a price without copying the link</h1>
      <p>
        A bookmarklet is a bookmark that runs a tiny script. Add this one, and on
        any Amazon.ca product page you click it once — {brand} opens with that
        product already checked. No extension, no permissions.
      </p>

      <section className="privacy-section">
        <h2>Add it</h2>
        <ol>
          <li>Make your bookmarks bar visible (⌘/Ctrl + Shift + B).</li>
          <li>
            Drag this button onto the bar:
            <BookmarkletLink siteUrl={site} />
          </li>
          <li>
            Can&apos;t drag? Press <strong>Copy code</strong>, then create a new
            bookmark by hand and paste it as the URL.
          </li>
        </ol>
      </section>

      <section className="privacy-section">
        <h2>Use it</h2>
        <p>
          On an Amazon.ca product page, click the <strong>SaveIQ price check</strong>{" "}
          bookmark. A new tab opens with the buy/wait verdict, the 90-day range,
          and the option to set a price-drop alert.
        </p>
      </section>

      <p className="privacy-section">
        Prefer to paste? <Link href="/">The homepage box does the same thing.</Link>
      </p>
    </main>
  );
}
