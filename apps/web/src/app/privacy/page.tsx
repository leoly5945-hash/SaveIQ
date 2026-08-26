import Link from "next/link";
import type { Metadata } from "next";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

export const metadata: Metadata = {
  title: `Privacy — ${brandName}`,
  description: "Draft privacy policy pending legal review.",
};

export default function PrivacyPage() {
  return (
    <main className="home-shell privacy-page">
      <p className="privacy-draft-banner">Draft — pending legal review</p>
      <p>
        <Link href="/">Back to {brandName}</Link>
      </p>
      <h1 className="home-title">Privacy Policy</h1>
      <p className="privacy-note">
        This page is a starter draft for a Canadian audience. It is not final
        legal advice and has not been reviewed by counsel.
      </p>

      <section className="privacy-section">
        <h2>Who we are</h2>
        <p>
          {brandName} helps people discover product and affiliate offers. We do
          not offer user accounts, login, or sign-up on this site.
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
        <p>We do not collect names, emails, phone numbers, or payment details on this page.</p>
      </section>

      <section className="privacy-section">
        <h2>Cookies and local storage</h2>
        <p>
          We use local storage for the anonymous identifier described above. We
          may use cookies or similar technologies for basic site operation and
          aggregated analytics. This draft does not describe a third-party ad
          tracker.
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
        <h2>Contact</h2>
        <p>Contact method TBD.</p>
      </section>
    </main>
  );
}
