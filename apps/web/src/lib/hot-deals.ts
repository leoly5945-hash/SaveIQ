export type HotDeal = {
  id: string;
  retailer: string;
  title: string;
  priceCents: number;
  wasCents: number;
  reason: string;
  tags: string[];
};

/**
 * Curated placeholder selection for the homepage "Hot right now" section.
 * The shape mirrors a ranked deal feed; swap this for a live trending
 * endpoint (e.g. GET /api/trending) once the backend exposes one.
 */
export const HOT_DEALS_SAMPLE: HotDeal[] = [
  {
    id: "xm5",
    retailer: "Best Buy Canada",
    title: "Sony WH-1000XM5 Wireless Headphones",
    priceCents: 29800,
    wasCents: 44800,
    reason: "Lowest price in 60 days · stacks with a $15 coupon",
    tags: ["Coupon", "Cashback"],
  },
  {
    id: "ninja",
    retailer: "Amazon.ca",
    title: "Ninja Air Fryer Pro 5.7L",
    priceCents: 10900,
    wasCents: 19900,
    reason: "Matches the Prime Day low · limited stock flagged",
    tags: ["Lightning deal"],
  },
  {
    id: "ghost16",
    retailer: "Sport Chek",
    title: "Brooks Ghost 16 Running Shoes",
    priceCents: 12200,
    wasCents: 17000,
    reason: "Below every other Canadian retailer right now",
    tags: ["Coupon"],
  },
  {
    id: "dysonv11",
    retailer: "Canadian Tire",
    title: "Dyson V11 Cordless Vacuum",
    priceCents: 54900,
    wasCents: 79900,
    reason: "Triangle offer adds about $40 back in points",
    tags: ["Points back"],
  },
  {
    id: "airwrap",
    retailer: "Sephora",
    title: "Dyson Airwrap Complete Long",
    priceCents: 62900,
    wasCents: 74900,
    reason: "Rare discount on an item that almost never goes on sale",
    tags: ["Gift with purchase"],
  },
  {
    id: "lg27",
    retailer: "Staples",
    title: 'LG 27" UltraGear 4K Monitor',
    priceCents: 37900,
    wasCents: 54900,
    reason: "Price dropped twice this week · trending down",
    tags: ["Cashback"],
  },
];
