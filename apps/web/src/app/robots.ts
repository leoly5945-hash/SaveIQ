import type { MetadataRoute } from "next";

import { getSiteUrl } from "@/lib/config";

export default function robots(): MetadataRoute.Robots {
  const site = getSiteUrl();
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Redirect hops, internal tooling and the JSON proxy are not content.
      disallow: ["/go/", "/internal/", "/api/"],
    },
    sitemap: `${site}/sitemap.xml`,
    host: site,
  };
}
