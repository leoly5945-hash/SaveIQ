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
  "sports-outdoors":
    "Fitness and camping basics — mats, bands, bottles, chairs — where you're paying for a known brand, not a gimmick. Each pick is a real product with the price we last checked and the date.",
  "pet-supplies":
    "Everyday dog and cat gear: chew toys, fetch tools, grooming, dental treats. Prices are a point-in-time snapshot from Amazon.ca; confirm the live price before ordering.",
  tools: "Hand tools and shop consumables — tape measures, utility knives, glue, WD-40 — the kind of thing you buy once and keep. Prices checked by hand, links go to Amazon.ca.",
  "toys-games":
    "Classic toys and games that have been around for decades — LEGO, Play-Doh, UNO, crayons. We check the current price and link straight to the product page.",
  baby: "Bottles, pacifiers, bath and drying-rack basics from established baby brands. Read the retailer's product details and return policy before you buy — prices here are a snapshot.",
};

export function categoryIntro(slug: string, fallbackName: string): string {
  return (
    CATEGORY_INTRO[slug] ??
    `Hand-checked ${fallbackName.toLowerCase()} deals. Prices are a point-in-time snapshot — confirm the current price at Amazon.ca before buying.`
  );
}
