import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

const CONTACT_NAME = "Leo Do";
const CONTACT_EMAIL = "leoly5945@gmail.com";
const OPERATOR_NAME = "Nextwave Software Company";
const LAST_UPDATED = "August 28, 2026";

export const metadata: Metadata = {
  title: `Privacy — ${brandName}`,
  description: "How SaveIQ collects and uses information.",
};

export default function PrivacyPage() {
  return (
    <main className="home-shell privacy-page">
      <p>
        <Link href="/">Back to {brandName}</Link>
        {" · "}
        <Link href="/terms">Terms of Use</Link>
      </p>
      <h1 className="home-title">Privacy Policy</h1>
      <p className="privacy-note">Last updated: {LAST_UPDATED}</p>

      <section className="privacy-section">
        <h2>Who we are</h2>
        <p>
          {brandName} ({`https://saveiq.ca`}) is an intermediary between
          shoppers and well-known retailers in Canada, using an AI routing
          system to help you find products at the best available price. It is
          operated by {OPERATOR_NAME} (4641 Dunbar St, Vancouver, BC, Canada).
          We do not offer user accounts, login, or sign-up on this site.
        </p>
      </section>

      <section className="privacy-section">
        <h2>What we collect</h2>
        <p>
          We generate an anonymous identifier in your browser and store it in
          local storage so we can attribute searches and outbound clicks without
          knowing who you are. We may also collect the search text you submit,
          offer identifiers you click, technical request data (such as time,
          referrer, and user agent), and similar usage analytics.
        </p>
        <p>We do not collect names, emails, phone numbers, or payment details through this site.</p>
      </section>

      <section className="privacy-section">
        <h2>Cookies and local storage</h2>
        <p>
          We use local storage for the anonymous identifier described above. We
          may use cookies or similar technologies for basic site operation and
          aggregated analytics. We do not run third-party advertising trackers.
        </p>
      </section>

      <section className="privacy-section">
        <h2>How we use information</h2>
        <p>
          Anonymous usage and click data help us rank offers, measure whether
          links work, and improve the product. We do not sell personal
          information.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Affiliate links and sharing</h2>
        <p>
          When you click an outbound offer link, the destination merchant (and
          any affiliate network connecting us to them) receives standard
          referral information about that click, so the merchant/network can
          attribute a resulting purchase to {brandName}. We do not sell or
          share the anonymous identifier described above for advertising
          purposes.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Data retention</h2>
        <p>
          We keep anonymous usage and click data only as long as useful for the
          purposes above, and delete or aggregate it afterward. Since we do not
          collect names or contact details through this site, there is no
          personal account data to retain or delete on request.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Your rights</h2>
        <p>
          If you are in Canada, Canadaʼs federal privacy law (PIPEDA) gives you
          the right to ask what information an organization holds about you and
          to file a complaint with the Office of the Privacy Commissioner of
          Canada. Because we only hold anonymous, non-identifying data, we
          generally have no way to look up a specific person&apos;s
          information — contact us if you believe this affects you.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Changes to this policy</h2>
        <p>
          We may update this page as the product changes. We&apos;ll update the
          &quot;Last updated&quot; date above when we do.
        </p>
      </section>

      <section className="privacy-section">
        <h2>Contact</h2>
        <p>
          Questions about this policy: {CONTACT_NAME},{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </section>
    </main>
  );
}
