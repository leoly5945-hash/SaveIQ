import Link from "next/link";

import { CONTACT_EMAIL, getBrandName } from "@/lib/config";
import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

const FOOTER_LINKS: { href: string; label: string }[] = [
  { href: "/guides", label: "Guides" },
  { href: "/deals", label: "Price Watch" },
  { href: "/tools", label: "Bookmarklet" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
  { href: "/editorial-guidelines", label: "Editorial Guidelines" },
  { href: "/affiliate-disclosure", label: "Affiliate Disclosure" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
];

export function SiteFooter() {
  const brandName = getBrandName();

  return (
    <footer className="home-footer site-footer">
      <div className="home-footer-org">
        <p className="home-footer-brand">{brandName}</p>
        <p>
          <strong>Nextwave Software Company</strong> (registered in Vietnam)
          {" · "}Vancouver, BC, Canada
          <br />
          Contact: Leo Do —{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </p>
        <p className="home-footer-links">
          {FOOTER_LINKS.map((link, index) => (
            <span key={link.href}>
              {index > 0 ? <span aria-hidden="true"> · </span> : null}
              <Link href={link.href}>{link.label}</Link>
            </span>
          ))}
        </p>
      </div>
      <p>{HOME_AFFILIATE_DISCLOSURE}</p>
      <p className="home-footer-legal">
        © 2026 Nextwave Software Company. All rights reserved.
      </p>
    </footer>
  );
}
