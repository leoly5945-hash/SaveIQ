import Link from "next/link";
import type { Metadata } from "next";

import { getApiBaseUrl, getBrandName } from "@/lib/config";

export const metadata: Metadata = {
  title: `Unsubscribe — ${getBrandName()}`,
  robots: { index: false, follow: false },
};

async function unsubscribe(token: string): Promise<boolean> {
  try {
    const url = new URL("/alerts/unsubscribe", getApiBaseUrl());
    url.searchParams.set("token", token);
    const res = await fetch(url, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function AlertsUnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  const ok = token ? await unsubscribe(token) : false;

  return (
    <main className="home-shell privacy-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <span>Unsubscribe</span>
      </nav>
      <h1 className="home-title">
        {ok ? "You're unsubscribed" : "Couldn't unsubscribe"}
      </h1>
      <p className="privacy-note">
        {ok
          ? "That price alert won&apos;t email you again."
          : "That link looks invalid or already used — no alert was changed."}
      </p>
      <p>
        <Link href="/watchlist">Manage everything you&apos;re tracking →</Link>
      </p>
    </main>
  );
}
