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

  const updated = new Intl.DateTimeFormat("en-CA", {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${guide.updated}T00:00:00Z`));

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
        </section>
      ))}

      {guide.relatedCategories && guide.relatedCategories.length > 0 ? (
        <section className="guide-related">
          <h2>Related deals</h2>
          <p className="guide-related-links">
            {guide.relatedCategories.map((cat) => (
              <Link href={categoryPath(cat)} key={cat}>
                {CATEGORY_LABEL[cat] ?? cat}
              </Link>
            ))}
          </p>
        </section>
      ) : null}

      <p className="guide-page-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
      <p className="deal-page-back">
        <Link href="/guides">← All guides</Link>
        {" · "}
        <Link href="/deals">Browse deals</Link>
      </p>
    </main>
  );
}
