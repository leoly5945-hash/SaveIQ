/**
 * Buying guides — plain, factual editorial content. Written to be genuinely
 * useful to a shopper, not to sell. No affiliate pressure, no invented stats.
 * Each guide links to the deal categories it relates to.
 */

export type GuideTable = { caption: string; headers: string[]; rows: string[][] };

export type GuideSection = { heading: string; body: string[]; table?: GuideTable };

export type GuideSource = { label: string; url: string };

export type Guide = {
  slug: string;
  title: string;
  description: string;
  updated: string; // ISO date
  checked?: string; // ISO date the prices/specs were last checked at the source
  sources?: GuideSource[];
  readMinutes: number;
  intro: string[];
  sections: GuideSection[];
  relatedCategories?: string[]; // category slugs
};

export const GUIDES: Guide[] = [
  {
    slug: "crypto-exchange-fees-canada-compared",
    title: "Crypto exchange fees in Canada compared: Kraken, NDAX, Newton, Shakepay and Crypto.com",
    description:
      "What Kraken, NDAX, Newton, Shakepay and Crypto.com publish about their trading costs at entry level, and why the numbers are not directly comparable.",
    updated: "2026-09-19",
    checked: "2026-09-19",
    readMinutes: 6,
    intro: [
      "This guide compares the entry-level trading costs that five crypto platforms authorized in Canada publish on their own pages. We have not opened accounts or traded on any of them, and every figure below comes from the platform’s own fee page, checked September 19, 2026. Fees change, so read the platform’s current page before you deposit.",
      "It is general information, not financial or investment advice, and we do not recommend that you buy, sell or hold any crypto asset. We did not compare Coinbase because its Canadian fee schedule could not be read without signing in, and we have not covered every platform on the Canadian Securities Administrators’ list.",
    ],
    sections: [
      {
        heading: "Entry-level trading costs",
        body: [
          "Each platform charges for trading in a different way, so read the “How you pay” column before comparing the numbers.",
        ],
        table: {
          caption: "Published entry-level trading costs, checked September 19, 2026",
          headers: ["Platform", "How you pay", "Entry-level figure"],
          rows: [
            ["Kraken (Kraken Pro spot)", "Maker and taker fees on each order", "0.40% maker and 0.80% taker at the lowest volume tier; 0.30% and 0.60% from US$2,500 of 30-day volume"],
            ["NDAX", "One flat trading fee", "0.20% on every buy and sell, with no volume tiers and no maker/taker split"],
            ["Newton", "Fee included in the quoted price, varying by asset", "1.00%–1.15% for BTC, ETH and USDC; 1.25%–1.45% for LTC, SOL and XLM; 1.50%–1.60% for other assets (Silver level)"],
            ["Shakepay", "A spread built into the buy or sell price, with no commission", "Targets a spread of 0.5%–2.0% over its benchmark price, which can rise by up to 1.5% more in adverse market conditions"],
            ["Crypto.com", "Not stated on the pages we read", "See Crypto.com’s own fee page for current trading costs"],
          ],
        },
      },
      {
        heading: "What a $1,000 trade could cost",
        body: [
          "To make the percentages concrete, here is the arithmetic on a $1,000 trade using the published figures. On NDAX, 0.20% is $2.00. On Kraken Pro at the lowest tier, a maker order at 0.40% costs $4.00 and a taker order at 0.80% costs $8.00. On Newton at the Silver level, 1.00% to 1.15% for Bitcoin is $10.00 to $11.50. On Shakepay, a spread of 0.5% to 2.0% is $5 to $20, and up to $35 if the spread widens by the full extra 1.5%.",
          "These are illustrations of the published rates, not quotes. Kraken’s figure is in US dollars for the volume tiers, and the actual cost depends on the pair, the order type and the price at the moment you trade.",
        ],
      },
      {
        heading: "Why the numbers are not directly comparable",
        body: [
          "A fee charged on the order and a spread built into the price are different things. With a fee, you see the price and the fee separately. With a spread, the cost sits in the gap between the price you pay and the reference price, which you have to look up yourself to measure.",
          "Kraken’s maker and taker fees also depend on whether your order adds liquidity to the order book (maker) or takes it (taker), and they fall as your 30-day volume grows. They apply to Kraken Pro; Kraken’s simpler Buy and Convert features are priced differently and are not covered here. Newton’s rates fall with your trailing 365-day volume. NDAX’s single rate does not change with volume. Check the current page of any platform before you rely on a figure here.",
        ],
      },
      {
        heading: "Costs beyond the trading fee",
        body: [
          "Deposit and withdrawal charges, network fees for moving crypto out, and any subscription can matter as much as the trading fee for small or occasional trades. Our guide to Interac e-Transfer funding lists the published deposit and CAD withdrawal costs for these platforms.",
        ],
      },
      {
        heading: "Risk warning",
        body: [
          "Crypto assets are volatile and can lose value quickly. Only use a platform that is authorized in Canada, and only risk money you can afford to lose. Nothing on SaveIQ is financial, investment, tax or legal advice.",
        ],
      },
    ],
    sources: [
      { label: "Kraken: fee schedule (Kraken Pro spot tiers, checked 2026-09-19)", url: "https://www.kraken.com/features/fee-schedule" },
      { label: "Kraken Support: how trading fees work on Kraken", url: "https://support.kraken.com/articles/201893638-how-trading-fees-work-on-kraken" },
      { label: "NDAX: fees (checked 2026-09-19)", url: "https://ndax.io/en/fees" },
      { label: "Newton Help Center: What are Newton’s fees? (checked 2026-09-19)", url: "https://help.newton.co/hc/en-us/articles/360052371793-What-are-Newton-s-Fees" },
      { label: "Shakepay Help Center: How does Shakepay make money? (checked 2026-09-19)", url: "https://help.shakepay.com/en/articles/3171250-how-does-shakepay-make-money" },
    ],
  },
  {
    slug: "interac-e-transfer-crypto-exchanges-canada",
    title: "Funding a crypto exchange with Interac e-Transfer: fees and limits in Canada",
    description:
      "The published Interac e-Transfer deposit fees, CAD withdrawal fees and limits at Kraken, NDAX, Newton, Shakepay and Crypto.com, and what to check before you send money.",
    updated: "2026-09-19",
    checked: "2026-09-19",
    readMinutes: 5,
    intro: [
      "Most Canadians fund a crypto platform with Interac e-Transfer. This guide lists what five platforms authorized in Canada publish about e-Transfer deposits, CAD withdrawals and limits, checked September 19, 2026 on each platform’s own pages. We have not tested any of them, and limits and fees change, so confirm them in your account before you send money.",
      "It is general information, not financial or investment advice. Your own bank may also charge fees for e-Transfers that are not shown here.",
    ],
    sections: [
      {
        heading: "Deposits and CAD withdrawals",
        body: [
          "Where a platform did not state a figure on the pages we read, the table says so instead of guessing.",
        ],
        table: {
          caption: "Published Interac e-Transfer and CAD withdrawal terms, checked September 19, 2026",
          headers: ["Platform", "Interac e-Transfer deposit", "CAD withdrawal"],
          rows: [
            ["Kraken", "Free. Limits of CAD 10,000 per transaction and per day, CAD 30,000 per week and CAD 100,000 per month; takes between an hour and a day", "CAD 10 fee via e-Transfer"],
            ["NDAX", "Free, processed in 0–30 minutes", "Interac e-Transfer CAD 1.50 with a CAD 10,000 limit; direct bank deposit (EFT) CAD 4.99"],
            ["Newton", "Free", "Interac e-Transfer free, EFT free; wire free for transfers of $10,000 or more, and a $35 fee for wires between $5,000 and $10,000"],
            ["Shakepay", "Free. Minimum $5 and maximum $10,000 per e-Transfer", "Outgoing e-Transfer limits are $5 to $10,000; no separate fee is listed on the fees page we read"],
            ["Crypto.com", "No Crypto.com fee for Interac Standard Transfer, though your bank might charge one. Minimum $20, up to $25,000 a day", "$1.99 CAD per withdrawal, with a daily maximum of $25,000 and review of up to 1–3 business days"],
          ],
        },
      },
      {
        heading: "What to check before you send money",
        body: [
          "Confirm the platform’s current limits in your own account, because a per-day or per-week limit can slow a larger deposit. Check the processing time for your first deposit, since new accounts can be reviewed more closely.",
          "Send the e-Transfer only to the address or contact the platform shows inside your logged-in account, and never to an address someone sends you by message or email. Then check for a withdrawal fee before you deposit, since a flat withdrawal fee matters more the smaller your balance is.",
        ],
      },
      {
        heading: "Crypto withdrawals are a separate cost",
        body: [
          "The table covers moving Canadian dollars. Moving crypto off a platform has its own network fees. For example, Newton says it covers up to $5 of network fees on your first crypto withdrawal each day, and charges a $10 CAD fee plus the network fee for its fastest Bitcoin lane. Check each platform’s crypto withdrawal terms as well.",
        ],
      },
      {
        heading: "Risk warning",
        body: [
          "Crypto assets are volatile and can lose value quickly. Only use a platform that is authorized in Canada, and only risk money you can afford to lose. Nothing on SaveIQ is financial, investment, tax or legal advice.",
        ],
      },
    ],
    sources: [
      { label: "Kraken Support: funding your account with an Interac e-Transfer (checked 2026-09-19)", url: "https://support.kraken.com/hc/en-us/articles/4412259063444-How-do-I-fund-my-account-with-an-Interac-e-Transfer-" },
      { label: "NDAX: fees (checked 2026-09-19)", url: "https://ndax.io/en/fees" },
      { label: "Newton Help Center: What are Newton’s fees? (checked 2026-09-19)", url: "https://help.newton.co/hc/en-us/articles/360052371793-What-are-Newton-s-Fees" },
      { label: "Shakepay: funding fees, limits and timeline (checked 2026-09-19)", url: "https://shakepay.com/fees" },
      { label: "Crypto.com Help Center: CAD deposit via Interac Standard Transfer (checked 2026-09-19)", url: "https://help.crypto.com/en/articles/4531462-cad-deposit-via-interac-standard-transfer" },
      { label: "Crypto.com Help Center: CAD withdrawal (checked 2026-09-19)", url: "https://help.crypto.com/en/articles/4533192-cad-withdrawal" },
    ],
  },
  {
    slug: "how-crypto-trading-fees-and-spreads-work",
    title: "How crypto trading fees, spreads and withdrawal costs work in Canada",
    description:
      "A plain-language explanation of maker and taker fees, spreads, flat fees, deposit and withdrawal charges, and how to compare the real cost of a crypto trade.",
    updated: "2026-09-19",
    readMinutes: 5,
    intro: [
      "Two crypto platforms can both say “low fees” and still cost very different amounts. The difference usually comes down to how the platform charges you. This guide explains the common ways, so you can read any platform’s fee page and work out what a trade would actually cost.",
      "It is general information, not financial or investment advice, and we do not recommend that you buy, sell or hold any crypto asset.",
    ],
    sections: [
      {
        heading: "A trading fee is charged on the order",
        body: [
          "Some platforms charge a percentage of each trade. A flat fee applies the same rate to every trade. A maker and taker model charges less if your order rests on the order book waiting to be matched (a maker order) and more if it is matched immediately against an existing order (a taker order). Maker and taker rates often fall as your trading volume over a recent period rises.",
          "The fee is shown separately from the price, so you can see what you paid for the asset and what you paid to trade it.",
        ],
      },
      {
        heading: "A spread is built into the price",
        body: [
          "Other platforms advertise no commission and earn a spread instead: the price you pay to buy is a little above a reference price, and the price you receive to sell is a little below it. There is no separate line item, so the cost is easy to miss. To estimate it, compare the platform’s buy or sell price with a widely quoted market price at the same moment.",
          "Some platforms publish a target range for their spread, and say it can widen when markets are volatile or liquidity is thin.",
        ],
      },
      {
        heading: "Costs around the trade",
        body: [
          "Deposit charges, Canadian-dollar withdrawal fees, network fees for sending crypto to another wallet, and subscriptions can all add to the total. For small or occasional trades, a flat withdrawal fee can outweigh a low trading fee, so add these up alongside the trading cost.",
          "Your own bank may also charge for e-Transfers or wires, which no platform’s fee page includes.",
        ],
      },
      {
        heading: "A worked example",
        body: [
          "Suppose you buy $1,000 of Bitcoin. A platform charging a flat 0.20% costs $2.00 to trade. A platform whose quoted price includes a 1.00% fee costs $10.00. A platform with a spread of 0.5% to 2.0% costs between $5 and $20, and you would only learn which by comparing its price with the market’s.",
          "Then add any deposit, withdrawal and network fees. The cheapest platform for a $1,000 purchase is not always the cheapest for a $50 purchase or a $50,000 one, because flat fees and volume tiers change the answer.",
        ],
      },
      {
        heading: "Where to find real figures",
        body: [
          "See our comparison of entry-level trading costs at platforms authorized in Canada, and our guide to Interac e-Transfer funding and CAD withdrawals. Both cite each platform’s own fee page and the date we checked it. To confirm that a platform is authorized in Canada, see our guide to the Canadian Securities Administrators’ list.",
        ],
      },
      {
        heading: "Risk warning",
        body: [
          "Crypto assets are volatile and can lose value quickly. Only use a platform that is authorized in Canada, and only risk money you can afford to lose. Nothing on SaveIQ is financial, investment, tax or legal advice.",
        ],
      },
    ],
  },
  {
    slug: "crypto-platforms-authorized-in-canada",
    title: "Which crypto platforms are authorized to serve Canadians?",
    description:
      "The platforms on the Canadian Securities Administrators’ list of crypto platforms authorized to do business with Canadians, what being listed does and does not mean, and how to check a platform yourself.",
    updated: "2026-09-19",
    checked: "2026-09-19",
    readMinutes: 4,
    intro: [
      "Canadian securities regulators require crypto platforms that serve Canadians to be authorized. The Canadian Securities Administrators (CSA), the umbrella group of the provincial and territorial regulators, publishes a list of the platforms that have received a decision allowing them to do business with Canadians.",
      "This guide reproduces that list as it stood on September 19, 2026, explains how to read it, and shows how to check any platform yourself. It is general information, not financial or investment advice, and we do not recommend that you buy, sell or hold any crypto asset.",
    ],
    sections: [
      {
        heading: "The CSA list",
        body: [
          "These are the entries on the CSA page, using the CSA’s own names and descriptions. Not every entry is a consumer exchange: some are lending platforms or infrastructure providers, and some are limited to certain provinces.",
        ],
        table: {
          caption:
            "Platforms listed by the Canadian Securities Administrators, checked September 19, 2026 (the CSA page shows “last updated September 18, 2026”)",
          headers: ["Name as listed by the CSA", "Listed as", "Limits shown by the CSA"],
          rows: [
            ["APX Inc.", "Crypto-backed lending platform", "None shown"],
            ["Coinbase Canada Inc.", "Crypto asset trading platform", "None shown"],
            ["Coinsquare Capital Markets Limited", "Crypto asset trading platform", "None shown"],
            ["Cybrid Canada Inc.", "Crypto asset trading platform", "Ontario only"],
            ["Fidelity Clearing Canada ULC", "Crypto asset trading platform", "None shown"],
            ["Fidelity Digital Assets Services", "Exempt marketplace and clearing agency; crypto asset trading platform", "None shown"],
            ["Foris DAX CAN ULC (Crypto.com)", "Crypto asset trading platform", "None shown"],
            ["Hibit Technology Ltd.", "Crypto asset trading platform", "Alberta, British Columbia, Manitoba and Saskatchewan only"],
            ["Payward Canada Inc. (Kraken)", "Crypto asset trading platform", "None shown"],
            ["Ndax Canada Inc.", "Crypto asset trading platform", "None shown"],
            ["Netcoins Inc.", "Crypto asset trading platform", "None shown"],
            ["Newton Crypto Ltd.", "Crypto asset trading platform", "None shown"],
            ["Satstreet Inc.", "Crypto asset trading platform", "Ontario, Alberta, British Columbia, Manitoba, Québec and Saskatchewan only"],
            ["Shakepay Inc.", "Crypto asset trading platform", "None shown"],
            ["Shakepay Credit Inc.", "Crypto-backed lending platform", "None shown"],
            ["VirgoCX", "Crypto asset trading platform", "Subject to terms requiring wind-down of its registrable business"],
            ["Wealthsimple Investments Inc.", "Crypto asset trading platform", "None shown"],
            ["Webull Canada Crypto Limited", "Crypto asset trading platform", "None shown"],
            ["zerohash llc", "Immediate delivery VRCA-trading platform", "None shown"],
          ],
        },
      },
      {
        heading: "What being on the list means, and what it does not",
        body: [
          "Being listed means a Canadian securities regulator has issued a decision allowing the platform to operate for Canadians, usually with terms and conditions attached. It is a minimum bar, not a seal of approval.",
          "It is not a recommendation from us, and it is not a guarantee of safety, service quality or returns. Crypto prices move sharply, and you can lose some or all of the money you put in. Read each platform’s fees and terms before you deposit anything, and read the CSA’s own decision if you want to know the conditions that apply.",
        ],
      },
      {
        heading: "Platforms that are not on the list",
        body: [
          "We did not find Binance, Bybit, OKX or KuCoin on the CSA list when we checked. If a platform that serves Canadians is not listed, check with your provincial securities regulator before you use it, and do not send it funds first.",
          "We only feature platforms from this list on SaveIQ, and we do not link to platforms that are not on it.",
        ],
      },
      {
        heading: "How to check a platform yourself",
        body: [
          "Open the CSA page linked under Sources and search it for the platform’s registered company name, which is often different from the brand name on its app. The list is updated when decisions change, so check again before you sign up rather than relying on this page.",
          "Also read what the entry says. A listing may be limited to certain provinces, may cover a lending product rather than an exchange, or may carry a wind-down condition, as VirgoCX’s does.",
        ],
      },
      {
        heading: "Risk warning",
        body: [
          "Crypto assets are volatile and can lose value quickly. Only use a platform that is authorized in Canada, and only risk money you can afford to lose. Nothing on SaveIQ is financial, investment, tax or legal advice.",
        ],
      },
    ],
    sources: [
      { label: "Canadian Securities Administrators: Crypto Platforms Authorized to Do Business with Canadians (checked 2026-09-19)", url: "https://www.securities-administrators.ca/crypto-platforms-regulation-and-enforcement-actions/crypto-platforms-authorized-to-do-business-with-canadians/" },
    ],
  },
  {
    slug: "samsung-galaxy-s26-canada-price-specs",
    title: "Samsung Galaxy S26 in Canada: price, specs and who it’s for",
    description:
      "Canadian list prices and published specifications for the Galaxy S26 family, what the differences add up to, and who each model suits.",
    updated: "2026-09-18",
    checked: "2026-09-18",
    readMinutes: 5,
    intro: [
      "This is a research guide, not a hands-on review. We have not tested the Galaxy S26. Everything below comes from the prices and specifications Samsung publishes for Canada, plus arithmetic on those numbers, and the source and date for each figure are listed at the end.",
      "Prices are a snapshot from September 18, 2026. Samsung, retailers and carriers change prices and promotions often, so confirm the current price before you buy.",
    ],
    sections: [
      {
        heading: "Canadian list prices",
        body: [
          "These are the prices Samsung Canada lists for outright purchase, in Canadian dollars. Samsung also shows monthly-payment options next to each price; check the term and the total you would pay before choosing one.",
        ],
        table: {
          caption: "Galaxy S26 family: Samsung Canada list prices (CAD), checked September 18, 2026",
          headers: ["Model", "Storage / RAM", "List price"],
          rows: [
            ["Galaxy S26 FE", "Starting configuration", "$1,049.99"],
            ["Galaxy S26", "256 GB / 12 GB", "$1,249.99"],
            ["Galaxy S26", "512 GB / 12 GB", "$1,529.99"],
            ["Galaxy S26+", "Starting configuration", "$1,529.99"],
            ["Galaxy S26 Ultra", "256 GB / 12 GB", "$1,899.99"],
            ["Galaxy S26 Ultra", "512 GB / 12 GB", "$2,179.99"],
            ["Galaxy S26 Ultra", "1 TB / 16 GB", "$2,599.99"],
          ],
        },
      },
      {
        heading: "The Galaxy S26 specifications that matter",
        body: [
          "Samsung’s own comparison lists these figures for the standard Galaxy S26. Battery-life figures are Samsung’s estimates and are not directly comparable with other brands’ figures, which use different test methods.",
        ],
        table: {
          caption: "Galaxy S26 published specifications (Samsung Canada)",
          headers: ["Spec", "Galaxy S26"],
          rows: [
            ["Display", "6.3-inch, 2340 x 1080 (FHD+) Dynamic AMOLED 2X"],
            ["Processor", "Snapdragon 8 Elite Gen 5 for Galaxy"],
            ["Rear cameras", "50 MP wide, 12 MP ultra wide, 10 MP telephoto (3x optical zoom)"],
            ["Front camera", "12 MP"],
            ["Battery", "4,300 mAh; Samsung estimates up to 31 hours of video playback"],
            ["Weight", "167 g"],
          ],
        },
      },
      {
        heading: "What the price gaps buy you",
        body: [
          "Going from the Galaxy S26 to the S26+ costs $280 at the starting configuration ($1,249.99 to $1,529.99). Samsung’s specifications show what that money changes: a 6.7-inch QHD+ (3120 x 1440) display instead of a 6.3-inch FHD+ one, a 4,900 mAh battery instead of 4,300 mAh, and a heavier phone at 190 g instead of 167 g. The processor and camera resolutions are the same on both.",
          "Doubling the Galaxy S26’s storage from 256 GB to 512 GB is also $280. The Galaxy S26 FE is $200 below the S26 at its starting price, with a 6.7-inch FHD+ display, a 4,900 mAh battery and a different processor (Exynos 2500).",
          "The S26 Ultra starts $650 above the S26 and $370 above the S26+ at 256 GB. Samsung lists it at 214 g with a 5,000 mAh battery. See Samsung’s comparison tool for its full specification list.",
        ],
      },
      {
        heading: "Who the Galaxy S26 suits",
        body: [
          "On the numbers, the standard S26 is the compact choice. At 167 g it is the lightest phone in Samsung’s S26 line-up, and it has the same processor as the S26+. It suits someone who wants a flagship-class chip without a large, heavy phone.",
          "It is a weaker fit if a bigger screen or a larger battery matters more than size: the S26+ offers both for $280 more, and the S26 FE offers a large screen for less, with a different processor.",
        ],
      },
      {
        heading: "What we haven’t tested",
        body: [
          "We haven’t measured battery life, camera quality, performance or display brightness. Samsung notes its battery estimates come from testing on pre-release units, and real-world results depend on network, settings and usage. For those questions, rely on independent lab tests and reviewers who have used the phone, and read more than one.",
        ],
      },
      {
        heading: "Before you buy in Canada",
        body: [
          "Samsung’s page lists some colours as available only at Samsung.com and Samsung Experience Stores, and shows a trade-in credit (up to $490 on the Galaxy S26 FE when we checked). Trade-in values depend on the device you trade in.",
          "Compare an unlocked phone with a carrier plan on the total cost over the full term, not the monthly figure alone. Then read the retailer’s return policy: it is part of the price.",
        ],
      },
    ],
    sources: [
      { label: "Samsung Canada: Galaxy S26, S26+ and S26 FE (buy page, checked 2026-09-18)", url: "https://www.samsung.com/ca/smartphones/galaxy-s26/buy/" },
      { label: "Samsung Canada: Galaxy S26 Ultra (buy page, checked 2026-09-18)", url: "https://www.samsung.com/ca/smartphones/galaxy-s26-ultra/buy/" },
      { label: "MobileSyrup: Galaxy S26 series Canadian pricing (February 25, 2026)", url: "https://mobilesyrup.com/2026/02/25/samsung-galaxy-s26-series-pricing-canada/" },
    ],
    relatedCategories: ["electronics"],
  },
  {
    slug: "which-samsung-galaxy-phone-to-buy-canada",
    title: "Which Samsung Galaxy S26 should you buy in Canada?",
    description:
      "A plain guide to choosing between the Galaxy S26, S26+, S26 FE and S26 Ultra in Canada, with the price gaps and what each step up changes.",
    updated: "2026-09-18",
    checked: "2026-09-18",
    readMinutes: 5,
    intro: [
      "Samsung sells four Galaxy S26 models in Canada, and the price range from the cheapest to the dearest is more than $1,500. This guide helps you decide how far up the range you actually need to go.",
      "It is built from Samsung Canada’s published prices and specifications, checked September 18, 2026. We have not tested the phones. Confirm current prices before you buy.",
    ],
    sections: [
      {
        heading: "The four models at a glance",
        body: [
          "Start with the physical size you are happy to carry, since that narrows the choice faster than any spec.",
        ],
        table: {
          caption: "Galaxy S26 family: Samsung Canada published figures, checked September 18, 2026",
          headers: ["Model", "Display", "Weight", "Battery", "Starting price"],
          rows: [
            ["Galaxy S26", "6.3-inch FHD+", "167 g", "4,300 mAh", "$1,249.99"],
            ["Galaxy S26 FE", "6.7-inch FHD+", "193 g", "4,900 mAh", "$1,049.99"],
            ["Galaxy S26+", "6.7-inch QHD+", "190 g", "4,900 mAh", "$1,529.99"],
            ["Galaxy S26 Ultra", "See Samsung’s page", "214 g", "5,000 mAh", "$1,899.99"],
          ],
        },
      },
      {
        heading: "Is the S26+ worth $280 more than the S26?",
        body: [
          "Only if you want the bigger screen and battery. For $280 more you get a 6.7-inch QHD+ display (3120 x 1440) rather than a 6.3-inch FHD+ one, and a 4,900 mAh battery rather than 4,300 mAh. Both phones use the same Snapdragon 8 Elite Gen 5 for Galaxy processor and have the same camera resolutions, so if you do not need the larger screen or battery, the standard S26 does the same job for less.",
        ],
      },
      {
        heading: "Where the S26 FE fits",
        body: [
          "The S26 FE is $200 cheaper than the S26 at its starting price and has a large 6.7-inch screen and a 4,900 mAh battery. The trade-off Samsung lists is a different processor, the Exynos 2500, and a slightly lower video-playback estimate (29 hours against 31). It is the option to look at if screen size and price matter more than having the S26’s chip.",
        ],
      },
      {
        heading: "Do you need 512 GB?",
        body: [
          "Doubling storage on the S26 from 256 GB to 512 GB costs $280 ($1,249.99 to $1,529.99). Choose 512 GB if you record a lot of video, keep large offline libraries, or plan to keep the phone for many years. If most of your photos and files live in the cloud, 256 GB is usually enough.",
        ],
      },
      {
        heading: "What the S26 Ultra adds",
        body: [
          "The Ultra starts at $1,899.99, which is $650 above the S26 and $370 above the S26+. Samsung lists it at 214 g with a 5,000 mAh battery. Compare its full specification sheet on Samsung’s site and decide whether the features that differ are ones you would use every week, since that is what you are paying the extra for.",
        ],
      },
      {
        heading: "Unlocked, carrier plan or trade-in",
        body: [
          "Samsung lists monthly-payment options beside each price. Add up the full amount you would pay over the whole term and compare it with the outright price, and check whether the phone is locked to the carrier.",
          "Samsung’s page shows a trade-in credit on the Galaxy S26 FE of up to $490 with an eligible device; the amount depends on what you trade in and its condition.",
        ],
      },
      {
        heading: "Should you wait for a lower price?",
        body: [
          "Samsung’s list prices for the S26, S26+ and S26 Ultra were the same on September 18, 2026 as the launch prices MobileSyrup reported in February. That suggests Samsung’s own list price has not moved. Retailer and carrier promotions are separate and change often, so compare the same model and storage across stores before you buy.",
        ],
      },
    ],
    sources: [
      { label: "Samsung Canada: Galaxy S26, S26+ and S26 FE (buy page, checked 2026-09-18)", url: "https://www.samsung.com/ca/smartphones/galaxy-s26/buy/" },
      { label: "Samsung Canada: Galaxy S26 Ultra (buy page, checked 2026-09-18)", url: "https://www.samsung.com/ca/smartphones/galaxy-s26-ultra/buy/" },
      { label: "MobileSyrup: Galaxy S26 series Canadian pricing (February 25, 2026)", url: "https://mobilesyrup.com/2026/02/25/samsung-galaxy-s26-series-pricing-canada/" },
    ],
    relatedCategories: ["electronics"],
  },
  {
    slug: "galaxy-s26-vs-iphone-17-vs-pixel-10-canada",
    title: "Galaxy S26 vs iPhone 17 vs Pixel 10 in Canada: prices and specs compared",
    description:
      "The Samsung Galaxy S26, Apple iPhone 17 and Google Pixel 10 side by side: Canadian prices and manufacturer-published specifications, with what the differences mean.",
    updated: "2026-09-18",
    checked: "2026-09-18",
    readMinutes: 6,
    intro: [
      "These three phones are the standard-size flagships from Samsung, Apple and Google. This guide compares the prices each company lists in Canada and the specifications each publishes, checked September 18, 2026. We have not tested any of them.",
      "Two cautions apply throughout. Each maker measures battery life its own way, so those figures are not directly comparable. And the prices below are starting prices, so compare storage tiers before you conclude one phone is cheaper.",
    ],
    sections: [
      {
        heading: "Canadian prices",
        body: [
          "The Galaxy S26 (256 GB) is $49.01 cheaper than the iPhone 17 (256 GB) at list price. Google’s page shows the Pixel 10 “from” $1,099 but does not state the storage tier at that price on the page we read, so check the storage before comparing it with the other two.",
        ],
        table: {
          caption: "List prices in CAD from each maker’s Canadian store, checked September 18, 2026",
          headers: ["Phone", "Starting price", "Storage at that price"],
          rows: [
            ["Samsung Galaxy S26", "$1,249.99", "256 GB"],
            ["Apple iPhone 17", "$1,299.00", "256 GB"],
            ["Google Pixel 10", "$1,099.00", "Not stated on the page we read"],
          ],
        },
      },
      {
        heading: "Specifications side by side",
        body: [
          "All figures below are as published by each manufacturer for Canada.",
        ],
        table: {
          caption: "Manufacturer-published specifications",
          headers: ["Spec", "Galaxy S26", "iPhone 17", "Pixel 10"],
          rows: [
            ["Display", "6.3-inch, 2340 x 1080 Dynamic AMOLED 2X", "6.3-inch, 2622 x 1206 OLED, ProMotion up to 120 Hz", "160 mm (about 6.3-inch), 1080 x 2424 OLED, 60–120 Hz"],
            ["Processor", "Snapdragon 8 Elite Gen 5 for Galaxy", "A19", "Google Tensor G5"],
            ["Weight", "167 g", "177 g", "204 g"],
            ["Battery", "4,300 mAh", "Capacity not published; up to 30 hours video playback (Apple)", "4,970 mAh typical"],
          ],
        },
      },
      {
        heading: "What the differences add up to",
        body: [
          "Size and weight are the clearest gap. The Galaxy S26 is the lightest at 167 g; the iPhone 17 is 10 g heavier at 177 g; the Pixel 10 is 204 g, which is 37 g heavier than the Galaxy S26. If you carry the phone in a small pocket all day, that matters.",
          "Battery capacity in mAh only compares like with like. The Pixel 10 has the largest published capacity, but the phones use different chips and software, and Apple does not publish a capacity at all. For battery life, look for independent tests that ran the same workload on all three.",
          "All three use roughly 6.3-inch OLED panels, so screen size is unlikely to separate them. Resolution and refresh-rate details differ between the makers’ spec sheets, and we have not compared the screens side by side.",
        ],
      },
      {
        heading: "Which should you choose?",
        body: [
          "The biggest factor is usually the ecosystem you already live in. If your laptop, watch, earbuds and family sharing are Apple, the iPhone 17 is the smoother fit. If you use Google services heavily, the Pixel 10 is built around them. If you want an Android phone from a company that also makes its own TVs, tablets and wearables, the Galaxy S26 fits that.",
          "If weight and pocket size are your priority, the specifications favour the Galaxy S26. If price is the deciding factor, check the Pixel 10’s storage tier and any current promotion on all three before you decide.",
        ],
      },
    ],
    sources: [
      { label: "Samsung Canada: Galaxy S26 (buy page, checked 2026-09-18)", url: "https://www.samsung.com/ca/smartphones/galaxy-s26/buy/" },
      { label: "Apple Canada: iPhone 17 (buy page and technical specifications, checked 2026-09-18)", url: "https://www.apple.com/ca/iphone-17/specs/" },
      { label: "Google Store Canada: Pixel 10 (price and specifications, checked 2026-09-18)", url: "https://store.google.com/ca/product/pixel_10_specs?hl=en-CA" },
    ],
    relatedCategories: ["electronics"],
  },
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
