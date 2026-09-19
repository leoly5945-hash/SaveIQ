import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getSiteUrl } from "@/lib/config";
import { AMAZON_ASSOCIATE_DISCLOSURE, categoryPath } from "@/lib/featured-deals";
import { GUIDES, getGuide } from "@/lib/guides";
import { safeJsonLd } from "@/lib/json-ld";

export const dynamic = "force-static";

export function generateStaticParams() {
  return GUIDES.map((g) => ({ slug: g.slug }));
}

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) {
    return { title: "Guide not found — SaveIQ" };
  }
  return {
    title: `${guide.title} | SaveIQ`,
    description: guide.description,
    alternates: { canonical: `/guide/${guide.slug}` },
    openGraph: {
      title: guide.title,
      description: guide.description,
      url: `${getSiteUrl()}/guide/${guide.slug}`,
      type: "article",
    },
  };
}

const CATEGORY_LABEL: Record<string, string> = {
  electronics: "Electronics",
  home: "Home",
  kitchen: "Kitchen",
  office: "Office",
  "personal-care": "Personal Care",
};

export default async function GuidePage({ params }: Params) {
  const { slug } = await params;
  const guide = getGuide(slug);
  if (!guide) {
    notFound();
  }

  const site = getSiteUrl();
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Article",
        headline: guide.title,
        description: guide.description,
        dateModified: guide.updated,
        datePublished: guide.updated,
        author: { "@type": "Organization", name: "SaveIQ" },
        publisher: { "@type": "Organization", name: "SaveIQ" },
        mainEntityOfPage: `${site}/guide/${guide.slug}`,
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Guides", item: `${site}/guides` },
          {
            "@type": "ListItem",
            position: 2,
            name: guide.title,
            item: `${site}/guide/${guide.slug}`,
          },
        ],
      },
    ],
  };

  const formatDate = (iso: string) =>
    new Intl.DateTimeFormat("en-CA", {
      dateStyle: "long",
      timeZone: "UTC",
    }).format(new Date(`${iso}T00:00:00Z`));
  const updated = formatDate(guide.updated);

  return (
    <main className="home-shell guide-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
      />

      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <Link href="/guides">Guides</Link>
      </nav>

      <h1 className="home-title guide-page-title">{guide.title}</h1>
      <p className="guide-page-meta">
        {guide.readMinutes} min read · Updated {updated}
        {guide.checked
          ? ` · Prices and specifications checked ${formatDate(guide.checked)}`
          : null}
      </p>

      {guide.intro.map((p, i) => (
        <p className="guide-page-lead" key={i}>
          {p}
        </p>
      ))}

      {guide.sections.map((section) => (
        <section className="guide-section" key={section.heading}>
          <h2>{section.heading}</h2>
          {section.body.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          {section.table ? (
            <div className="guide-table-wrap">
              <table className="guide-table">
                <caption>{section.table.caption}</caption>
                <thead>
                  <tr>
                    {section.table.headers.map((header) => (
                      <th scope="col" key={header}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {section.table.rows.map((row) => (
                    <tr key={row.join("|")}>
                      {row.map((cell, i) => (
                        <td key={i}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ))}

      {guide.sources && guide.sources.length > 0 ? (
        <section className="guide-section guide-sources">
          <h2>Sources</h2>
          <ul>
            {guide.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} rel="noopener noreferrer" target="_blank">
                  {source.label}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {guide.relatedCategories && guide.relatedCategories.length > 0 ? (
        <section className="guide-related">
          <h2>Related price checks</h2>
          <p className="guide-related-links">
            {guide.relatedCategories.map((cat) => (
              <Link href={categoryPath(cat)} key={cat}>
                {CATEGORY_LABEL[cat] ?? cat}
              </Link>
            ))}
          </p>
        </section>
      ) : null}

      <p className="guide-page-disclosure">
        How we research: see our{" "}
        <Link href="/editorial-guidelines">Editorial Guidelines</Link> and{" "}
        <Link href="/affiliate-disclosure">Affiliate Disclosure</Link>.{" "}
        {AMAZON_ASSOCIATE_DISCLOSURE}
      </p>
      <p className="deal-page-back">
        <Link href="/guides">← All guides</Link>
        {" · "}
        <Link href="/deals">Price Watch</Link>
      </p>
    </main>
  );
}
