/**
 * Buying guides — plain, factual editorial content. Written to be genuinely
 * useful to a shopper, not to sell. No affiliate pressure, no invented stats.
 * Each guide links to the deal categories it relates to.
 */

export type GuideSection = { heading: string; body: string[] };

export type Guide = {
  slug: string;
  title: string;
  description: string;
  updated: string; // ISO date
  readMinutes: number;
  intro: string[];
  sections: GuideSection[];
  relatedCategories?: string[]; // category slugs
};

export const GUIDES: Guide[] = [
  {
    slug: "how-to-find-the-lowest-price-in-canada",
    title: "How to actually find the lowest price in Canada",
    description:
      "A practical checklist for telling a real price from a marked-up one — list prices, pack sizes, price history, shipping and returns.",
    updated: "2026-09-06",
    readMinutes: 6,
    intro: [
      "“Lowest price” is one of the most abused phrases in online shopping. A retailer can show a high “list” price next to a lower “sale” price and call the difference a saving, even if nobody has paid the list price in months. This guide is the checklist we use ourselves before calling something a good price.",
    ],
    sections: [
      {
        heading: "Ignore the list price, look at what people actually pay",
        body: [
          "The number that matters is the current selling price, not the struck-through one next to it. Manufacturer’s Suggested Retail Price (MSRP) is often set well above what any store charges, so a “40% off MSRP” banner can just mean “this is the normal price.”",
          "A quick sanity check: search the exact product name plus “price history”, or paste the product URL into a price-tracking tool. If the “sale” price is the same price it has been for the last three months, it is not a sale.",
        ],
      },
      {
        heading: "Compare price per unit, not price per package",
        body: [
          "Pack sizes change. A brand may quietly move a cereal box from 525 g to 475 g, or a pack of batteries from 24 to 20, while keeping the price the same or raising it. This is sometimes called shrinkflation.",
          "Always divide the price by the count or the weight and compare that figure. A 12-pack that costs a little more than an 8-pack is usually the better deal; a “value” multipack that works out to more per unit is not.",
        ],
      },
      {
        heading: "Add shipping, tax and the cost of returning it",
        body: [
          "A lower sticker price can lose to a higher one once shipping is added, especially below a free-shipping threshold. In Canada, remember GST/HST or PST/QST will be added at checkout on most goods.",
          "The return policy is part of the price. If one retailer offers free 30-day returns and another charges restocking or return shipping, the first is cheaper for anything you might send back — clothing, electronics, anything sized or fitted.",
        ],
      },
      {
        heading: "Check more than one retailer for the same item",
        body: [
          "Big Canadian retailers — Amazon.ca, Walmart.ca, Best Buy, Canadian Tire, Staples, Indigo — often carry the same national-brand product. Prices between them can differ by 10–20% on any given week, and the cheapest one rotates.",
          "For identical items, match the model number, not just the name. Retailers sometimes stock a slightly different SKU (a bundle, a colour, an older revision) that looks the same in a listing thumbnail.",
        ],
      },
      {
        heading: "Be wary of urgency",
        body: [
          "Countdown timers, “only 3 left” and “20 people are viewing this” are designed to stop you from comparing. A genuinely good price is still a good price an hour later after you have checked two other stores.",
          "If a deal is real and time-limited (a retailer’s published sale with a real end date), you lose nothing by taking ten minutes to confirm it against the regular price first.",
        ],
      },
    ],
    relatedCategories: ["electronics", "home", "kitchen"],
  },
  {
    slug: "usb-c-cables-what-the-specs-mean",
    title: "USB-C cables: what the specs actually mean",
    description:
      "USB-C is a connector shape, not a spec. Here is how to read charging wattage, data speed and cable length so you buy the right one.",
    updated: "2026-09-06",
    readMinutes: 5,
    intro: [
      "Two USB-C cables can look identical and behave completely differently. One might fast-charge a laptop; the other might only trickle-charge a phone and move data at 1998 speeds. The connector tells you nothing — the spec printed on the packaging does.",
    ],
    sections: [
      {
        heading: "Charging: look for the wattage",
        body: [
          "USB-C Power Delivery cables are rated for a maximum wattage: commonly 60 W, 100 W, or 240 W. A 60 W cable is fine for phones, tablets and small laptops. For a 13–16″ laptop that charges over USB-C, get 100 W. 240 W only matters for large gaming laptops.",
          "Cables rated above 60 W contain an “e-marker” chip that tells the charger how much power the cable can safely carry. A cheap unmarked cable may cap at 60 W regardless of what your charger can deliver.",
        ],
      },
      {
        heading: "Data: USB 2.0 vs 3.2 vs Thunderbolt",
        body: [
          "Many inexpensive USB-C cables are USB 2.0 for data — about 480 Mbps. That is fine for charging and for a keyboard or mouse, but slow for moving files off an external SSD.",
          "For fast external storage you want a cable labelled USB 3.2 Gen 2 (10 Gbps) or higher, or Thunderbolt / USB4 (40 Gbps). These cost more and are usually shorter, because high-speed signals degrade over distance.",
        ],
      },
      {
        heading: "“Charge only” cables exist",
        body: [
          "Some bundled cables carry power but not data, or data but not video. If you plan to connect a monitor over USB-C, check that the cable supports DisplayPort Alt Mode or is a full-featured Thunderbolt cable.",
        ],
      },
      {
        heading: "Length and build",
        body: [
          "For a desk or nightstand, 1–2 m is convenient. For a fast-data cable to an SSD, shorter is more reliable. Braided jackets and moulded strain relief at the connector are the parts that fail first on cheap cables — they are worth a couple of dollars extra.",
          "Brand matters less than the printed rating. A well-reviewed budget cable that clearly states “100 W” and “USB 2.0 data” is a known quantity; an unbranded cable with no rating is a guess.",
        ],
      },
    ],
    relatedCategories: ["electronics"],
  },
  {
    slug: "alkaline-vs-rechargeable-batteries",
    title: "Alkaline vs rechargeable AA/AAA batteries: which is cheaper",
    description:
      "The maths on disposable versus rechargeable batteries, and which devices each one actually suits.",
    updated: "2026-09-06",
    readMinutes: 5,
    intro: [
      "Rechargeable batteries cost more up front and less over time — but only if you use them in the right devices. For some things, disposable alkalines are genuinely the better choice.",
    ],
    sections: [
      {
        heading: "The cost-per-use maths",
        body: [
          "A disposable AA costs roughly 40–80 cents each in a multipack and is used once. A good rechargeable AA (NiMH) costs a few dollars but is rated for hundreds of charge cycles. Over its life it works out to a fraction of a cent per use, plus a small amount of electricity.",
          "The break-even point is usually reached within a year for anything you replace batteries in more than a few times a year.",
        ],
      },
      {
        heading: "Where rechargeables win",
        body: [
          "High-drain and frequently-used devices: game controllers, wireless mice and keyboards, camera flashes, kids’ toys, flashlights you actually use. These flatten disposables quickly, so the savings add up fast.",
          "Low-self-discharge NiMH cells (often sold “pre-charged”) hold most of their charge for months on the shelf, which removed the old complaint about rechargeables going flat in a drawer.",
        ],
      },
      {
        heading: "Where disposables still make sense",
        body: [
          "Low-drain, set-and-forget devices: smoke detectors, wall clocks, TV remotes, emergency flashlights. A disposable alkaline can last years in these, and you do not want a smoke detector on a battery that slowly self-discharges.",
          "Anything you need to work reliably after sitting unused — an emergency kit, a rarely-used tool — is better on fresh alkalines with a long printed shelf life.",
        ],
      },
      {
        heading: "Reading the shelf-life claim",
        body: [
          "“10-year shelf life” on alkaline packaging means the unused battery in storage, not the battery in your device. Once it is powering something, runtime depends entirely on the device’s draw.",
        ],
      },
    ],
    relatedCategories: ["home", "electronics"],
  },
  {
    slug: "cast-iron-vs-nonstick-for-beginners",
    title: "Cast iron vs nonstick: what a beginner actually needs",
    description:
      "Both have a place. Here is the honest trade-off on cost, maintenance and what each pan is good at.",
    updated: "2026-09-06",
    readMinutes: 5,
    intro: [
      "A well-known cast-iron skillet costs about the same as a mid-range nonstick pan, but they age in opposite directions: cast iron gets better with use, nonstick wears out. Neither is “best” — they do different jobs.",
    ],
    sections: [
      {
        heading: "What cast iron is good at",
        body: [
          "Searing steak, cornbread, frittatas, anything that goes from stovetop to oven, and holding heat evenly once it is hot. A basic pre-seasoned skillet can last decades and can be re-seasoned back to health if it is ever neglected.",
          "The maintenance is simpler than its reputation: hot water, a brush or chainmail scrubber, dry it on the burner, wipe a thin film of oil. Mild soap is fine on modern seasoning. It should not go in the dishwasher and should not soak.",
        ],
      },
      {
        heading: "What nonstick is good at",
        body: [
          "Eggs, delicate fish, pancakes, low-fat cooking, and quick cleanup. For a lot of everyday cooking a nonstick pan is simply less hassle.",
          "The trade-off is lifespan. Even a good nonstick coating degrades over a few years of normal use — faster with metal utensils, high heat or the dishwasher. Treat it as a consumable you replace, not an heirloom.",
        ],
      },
      {
        heading: "A sensible starter set",
        body: [
          "One 8–10″ cast-iron skillet and one 10–12″ nonstick frying pan covers most home cooking. Add a stainless steel pan later if you get into sauces and want to deglaze.",
          "You do not need an expensive brand for either. A basic pre-seasoned cast-iron skillet from a long-established maker and a mid-priced nonstick pan with a comfortable handle will do everything a beginner needs.",
        ],
      },
    ],
    relatedCategories: ["kitchen"],
  },
  {
    slug: "reading-an-amazon-listing-without-getting-fooled",
    title: "Reading an Amazon.ca listing without getting fooled",
    description:
      "How to check who is selling, whether the ‘list price’ is real, and whether the reviews belong to the product you are looking at.",
    updated: "2026-09-06",
    readMinutes: 6,
    intro: [
      "Most Amazon.ca listings are straightforward. A minority are set up to look better than they are. These are the checks that take thirty seconds and save you from the bad ones.",
    ],
    sections: [
      {
        heading: "Check who sells it and who ships it",
        body: [
          "Under the buy box it says “Ships from” and “Sold by”. “Sold by Amazon.ca” or a recognised brand store is the safest. An unfamiliar third-party seller is not automatically bad, but it is worth a look at the seller’s rating and how long they have been active.",
          "Returns and warranty handling can differ for third-party sellers, so read that section before buying anything expensive.",
        ],
      },
      {
        heading: "Treat the struck-through price with suspicion",
        body: [
          "A “List Price” or “was” price shown above the current price is not always a price the item recently sold at. If the discount looks large, check the price on another retailer or in a price-history tool before assuming it is a saving.",
        ],
      },
      {
        heading: "Make sure the reviews match the product",
        body: [
          "On listings with variations — sizes, colours, bundles — the star rating and review count are often shared across every variation. A cheap accessory can inherit thousands of reviews from an expensive main product.",
          "Read a few recent reviews and check they describe the exact thing you are buying. Watch for a sudden burst of five-star reviews on the same day, reviews that only mention “fast shipping”, or reviewers who were clearly given the product for free.",
        ],
      },
      {
        heading: "Use the product details, not the title",
        body: [
          "Scroll to the “Product information” table for the ASIN, model number, dimensions and material. Titles are stuffed with keywords and can be misleading; the spec table is usually accurate.",
          "If Amazon shows a “frequently returned item” note, take it seriously — it means a meaningfully higher share of buyers sent this one back.",
        ],
      },
    ],
    relatedCategories: ["electronics", "home", "kitchen", "office"],
  },
  {
    slug: "budget-skincare-the-four-that-do-the-work",
    title: "Budget skincare: the four products that do the work",
    description:
      "A no-nonsense routine — cleanser, moisturiser, sunscreen, one active — and why the cheaper versions are often the same ingredients.",
    updated: "2026-09-06",
    readMinutes: 5,
    intro: [
      "A skincare routine does not need ten steps or expensive bottles. Four categories cover what actually changes skin, and drugstore brands frequently use the same core ingredients as the premium ones.",
    ],
    sections: [
      {
        heading: "A gentle cleanser",
        body: [
          "The job is to remove dirt, oil and sunscreen without stripping the skin. A fragrance-free, non-foaming or gently-foaming cleanser is enough for most people. If your face feels tight and squeaky after washing, the cleanser is too harsh.",
        ],
      },
      {
        heading: "A moisturiser",
        body: [
          "Look for humectants (glycerin, hyaluronic acid) and, for drier skin, ceramides. A basic tub or pump that lists these near the top of the ingredients does the same work as a jar that costs five times more.",
          "Match the texture to your skin: a lightweight gel-cream for oily skin, a richer cream for dry.",
        ],
      },
      {
        heading: "Sunscreen",
        body: [
          "This is the single product with the most evidence behind it for preventing visible ageing and skin damage. A broad-spectrum SPF 30 or higher, worn daily, matters more than any serum. The best sunscreen is one whose texture you will actually re-apply.",
        ],
      },
      {
        heading: "One active, if you want one",
        body: [
          "Niacinamide is a mild, well-tolerated all-rounder for oil balance and tone. Retinoids are the most proven for lines and texture but need slow introduction. Vitamin C is popular for brightness. Pick one, use it consistently for a few months, and do not layer several strong actives at once.",
          "Inexpensive single-ingredient serums have made these actives cheap. The formulation quality of a well-reviewed budget niacinamide is fine; you are not missing much by skipping the luxury version.",
        ],
      },
    ],
    relatedCategories: ["personal-care"],
  },
];

export function getGuide(slug: string): Guide | undefined {
  return GUIDES.find((g) => g.slug === slug);
}

export function guidePath(slug: string): string {
  return `/guide/${slug}`;
}

export function guidesForCategory(categorySlug: string): Guide[] {
  return GUIDES.filter((g) => g.relatedCategories?.includes(categorySlug));
}
