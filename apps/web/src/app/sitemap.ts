import type { MetadataRoute } from "next";

import { getSiteUrl } from "@/lib/config";
import { fetchDealCategories, fetchDeals } from "@/lib/featured-deals";
import { GUIDES } from "@/lib/guides";

// Build fresh each request so newly-added deals/categories appear immediately.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const site = getSiteUrl();
  const now = new Date();

  const staticPages: MetadataRoute.Sitemap = [
    { url: `${site}/`, lastModified: now, changeFrequency: "daily", priority: 1 },
    {
      url: `${site}/deals`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${site}/guides`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${site}/about`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${site}/privacy`,
      lastModified: now,
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${site}/terms`,
      lastModified: now,
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];

  const [deals, categories] = await Promise.all([
    fetchDeals(),
    fetchDealCategories(),
  ]);

  const categoryPages: MetadataRoute.Sitemap = categories.map((cat) => ({
    url: `${site}/category/${cat.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.7,
  }));

  const dealPages: MetadataRoute.Sitemap = deals.map((deal) => ({
    url: `${site}/deal/${deal.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  const guidePages: MetadataRoute.Sitemap = GUIDES.map((guide) => ({
    url: `${site}/guide/${guide.slug}`,
    lastModified: new Date(`${guide.updated}T00:00:00Z`),
    changeFrequency: "monthly",
    priority: 0.6,
  }));

  return [...staticPages, ...guidePages, ...categoryPages, ...dealPages];
}
