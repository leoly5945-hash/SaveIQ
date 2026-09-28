import Link from "next/link";

import { PriceDropGrid } from "@/components/price-drops";
import {
  AMAZON_ASSOCIATE_DISCLOSURE,
  fetchPriceDrops,
  PRICE_DROPS_BLURB,
  PRICE_DROPS_HEADING,
} from "@/lib/featured-deals";

/** Homepage strip: rendered only on days something actually qualifies. */
export async function HomePriceDrops() {
  const deals = await fetchPriceDrops(6);
  if (deals.length === 0) {
    return null;
  }
  return (
    <section className="home-featured" aria-labelledby="price-drops-heading">
      <div className="home-featured-head">
        <h2 id="price-drops-heading">{PRICE_DROPS_HEADING}</h2>
        <p>{PRICE_DROPS_BLURB}</p>
      </div>
      <PriceDropGrid deals={deals} />
      <p className="home-featured-more">
        <Link href="/deals">See every price check →</Link>
      </p>
      <p className="home-featured-disclosure">{AMAZON_ASSOCIATE_DISCLOSURE}</p>
    </section>
  );
}
