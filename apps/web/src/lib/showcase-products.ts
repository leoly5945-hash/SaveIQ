/**
 * Hand-picked ASINs for the homepage "compare across stores" section.
 *
 * Chosen because a real cross-merchant comparison already comes back for
 * them (verified against production before adding) — general electronics
 * that big-box retailers also carry, unlike the FeaturedDeals set (cheap
 * household/office items Amazon dominates, where a match rarely exists).
 * No revenue requirement here: these render whatever merchants the
 * comparison engine finds, tagged or not — the point is variety and clicks,
 * not affiliate commission.
 *
 * A short label is just a hint for the card; nothing enforces it.
 */
export const SHOWCASE_ASINS: readonly string[] = [
  "B0CT9552BL", // Dyson V8 Plus Cordless Vacuum
  "B0CT97D9R2", // Dyson V15 Detect Plus Cordless Vacuum
  "B0F1GF1KFC", // Dell 27" 4K Monitor
  "B07R295MLS", // eufy 11S MAX Robot Vacuum
  "B086PKMZ21", // Razer BlackShark V2 X Gaming Headset
  "B0F66NH2ZX", // Anker Prime Power Bank
  "B09B8V1LZ3", // Amazon Echo Dot
];
