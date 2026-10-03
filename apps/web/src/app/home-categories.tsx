import Link from "next/link";

import { ProductArt } from "@/components/product-art";
import { categoryPath, fetchDealCategories } from "@/lib/featured-deals";

/**
 * Homepage category tiles. Only categories that actually have products on the
 * Price Watch list are shown, each with its real product count.
 */
export async function HomeCategories() {
  const categories = await fetchDealCategories();
  if (categories.length === 0) {
    return null;
  }
  return (
    <section className="hp-cats" aria-labelledby="categories-heading">
      <div className="hp-section-head">
        <div>
          <h2 id="categories-heading">Explore categories</h2>
          <p>Everyday products we price-check every morning.</p>
        </div>
        <Link className="hp-more" href="/deals">
          View all price checks →
        </Link>
      </div>
      <ul className="hp-cat-list">
        {categories.map((cat) => (
          <li key={cat.slug}>
            <Link className="hp-cat" href={categoryPath(cat.slug)}>
              <ProductArt categorySlug={cat.slug} size="tile" />
              <span className="hp-cat-name">{cat.name}</span>
              <span className="hp-cat-count">
                {cat.count} {cat.count === 1 ? "product" : "products"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
