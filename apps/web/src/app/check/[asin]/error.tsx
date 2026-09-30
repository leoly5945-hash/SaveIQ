"use client";

import Link from "next/link";

export default function CheckError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="home-shell privacy-page">
      <p className="crumbs">
        <Link href="/">SaveIQ</Link> <span aria-hidden="true">/</span> Price check
      </p>
      <h1>We couldn&apos;t load the price data right now</h1>
      <p>Our price source is busy for a moment. This usually clears within a minute.</p>
      <p>
        <button type="button" className="home-submit" onClick={() => reset()}>
          Try again
        </button>
      </p>
      <p>
        Or <Link href="/">check a different product</Link>.
      </p>
    </main>
  );
}
