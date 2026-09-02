/**
 * Short, honest intro copy for each deal category. Kept factual on purpose —
 * these pages exist to help someone browse, not to oversell.
 */
export const CATEGORY_INTRO: Record<string, string> = {
  electronics:
    "Cables, chargers, and accessories where the list price and the everyday price often drift apart. We check the current Amazon.ca price by hand and link straight to the product so you can confirm it before buying.",
  home: "Small household items — adhesives, batteries, cleaning basics — that are easy to overpay for. Each pick is a real product with the price we last verified and the date we checked it.",
  kitchen:
    "Everyday kitchen tools we've price-checked on Amazon.ca. Nothing here is on a countdown timer; the price is a snapshot and the link takes you to the retailer to see the live figure.",
  office:
    "Pens, markers, pencils, and sticky notes — the kind of low-cost supplies where a few dollars' difference adds up over a bulk pack. Prices checked by hand, links go to Amazon.ca.",
  "personal-care":
    "Skincare and oral-care staples from names you already know. We list the price we verified and when; confirm the current price and read the retailer's return policy before you order.",
};

export function categoryIntro(slug: string, fallbackName: string): string {
  return (
    CATEGORY_INTRO[slug] ??
    `Hand-checked ${fallbackName.toLowerCase()} deals. Prices are a point-in-time snapshot — confirm the current price at Amazon.ca before buying.`
  );
}
