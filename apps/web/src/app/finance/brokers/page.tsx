import Link from "next/link";
import type { Metadata } from "next";

import { FINANCE_PAGES } from "@/lib/finance";

import { FinancePageBody } from "../finance-page-content";

const content = FINANCE_PAGES.brokers;

const DESCRIPTION =
  "Trading commissions, account fees and FX costs from Canadian stock brokers, compared side by side.";

// Placeholder rows (see lib/finance.ts) — noindex until real, verified data
// from an approved affiliate programme replaces them.
export const metadata: Metadata = {
  title: "Compare Stock Brokers | SaveIQ Finance",
  description: DESCRIPTION,
  alternates: { canonical: content.path },
  robots: { index: false, follow: false },
};

export default function BrokersPage() {
  return (
    <main className="home-shell finance-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <Link href="/finance">Finance</Link>
        <span aria-hidden="true"> / </span>
        <span>Stock Brokers</span>
      </nav>

      <FinancePageBody content={content} />
    </main>
  );
}
