import { formatMoney } from "@/lib/home-recommendations";
import { HOT_DEALS_SAMPLE } from "@/lib/hot-deals";

export function HotDeals() {
  const deals = HOT_DEALS_SAMPLE;
  if (deals.length === 0) {
    return null;
  }

  return (
    <section className="home-hot">
      <div className="home-hot-head">
        <h2>Hot right now</h2>
        <p>Picked by SaveIQ AI across retailers. Sample selection.</p>
      </div>
      <ul className="home-hot-grid">
        {deals.map((deal) => {
          const percentOff =
            deal.wasCents > 0
              ? Math.round((1 - deal.priceCents / deal.wasCents) * 100)
              : 0;
          return (
            <li className="home-hot-card" key={deal.id}>
              {percentOff > 0 ? (
                <span className="home-discount">−{percentOff}%</span>
              ) : null}
              <p className="merchant-name">{deal.retailer}</p>
              <h3>{deal.title}</h3>
              <div className="home-price-row">
                <p className="price">{formatMoney(deal.priceCents, "CAD")}</p>
                <p className="compare-price">
                  was {formatMoney(deal.wasCents, "CAD")}
                </p>
              </div>
              <p className="home-hot-reason">{deal.reason}</p>
              <div className="badge-row">
                {deal.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
