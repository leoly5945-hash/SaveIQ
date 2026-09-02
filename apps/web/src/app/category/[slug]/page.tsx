import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DealGrid } from "@/components/deal-card";
import { getSiteUrl } from "@/lib/config";
import { categoryIntro } from "@/lib/deal-categories";
import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  fetchDealCategories,
  fetchDeals,
} from "@/lib/featured-deals";

export const revalidate = 3600;

type Params = { params: Promise<{ slug: string }> };

async function resolveCategory(slug: string) {
  const categories = await fetchDealCategories();
  return categories.find((c) => c.slug === slug) ?? null;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const category = await resolveCategory(slug);
  if (!category) {
    return { title: "Category not found — SaveIQ" };
  }
  return {
    title: `${category.name} deals in Canada | SaveIQ`,
    description: categoryIntro(slug, category.name),
    alternates: { canonical: `/category/${slug}` },
    openGraph: {
      title: `${category.name} deals — SaveIQ`,
      description: categoryIntro(slug, category.name),
      url: `${getSiteUrl()}/category/${slug}`,
      type: "website",
    },
  };
}

export default async function CategoryPage({ params }: Params) {
  const { slug } = await params;
  const category = await resolveCategory(slug);
  if (!category) {
    notFound();
  }

  const deals = await fetchDeals({ category: slug });

  return (
    <main className="home-shell category-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">SaveIQ</Link>
        <span aria-hidden="true"> / </span>
        <Link href="/deals">Deals</Link>
        <span aria-hidden="true"> / </span>
        <span>{category.name}</span>
      </nav>

      <h1 className="home-title category-page-title">
        {category.name} deals
      </h1>
      <p className="category-page-intro">{categoryIntro(slug, category.name)}</p>

      {deals.length > 0 ? (
        <DealGrid deals={deals} />
      ) : (
        <p className="state-message">No deals in this category right now.</p>
      )}

      <p className="category-page-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
      <p className="deal-page-back">
        <Link href="/deals">← All deals</Link>
      </p>
    </main>
  );
}
