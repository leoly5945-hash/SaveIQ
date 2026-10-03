// Data model + placeholder content for the Finance hub (/finance, /finance/*).
//
// IMPORTANT: every row below is a PLACEHOLDER, not a real issuer/exchange/
// broker fee. SaveIQ's own /about page promises "every price we show is a
// real price we checked by hand" — do not let this fake data reach
// production. Each finance page sets `robots: { index: false }` for the
// same reason; remove that once FINANCE_ROWS is replaced with real,
// verified data from an approved affiliate programme.

export type FinanceVertical = "credit-cards" | "crypto" | "brokers";

export type FinanceColumn = {
  key: string;
  label: string;
};

export type FinanceRow = {
  id: string;
  name: string;
  initial: string;
  values: Record<string, string>;
  bestFor: string;
  ctaLabel: string;
};

export type FinanceMatchQuestion = {
  prompt: string;
  options: string[];
};

export type FinancePageContent = {
  vertical: FinanceVertical;
  path: string;
  navLabel: string;
  eyebrow: string;
  title: string;
  subhead: string;
  matchTitle: string;
  matchQuestion: FinanceMatchQuestion;
  compareTitle: string;
  compareSubhead: string;
  searchPlaceholder: string;
  filters: string[];
  columns: FinanceColumn[];
  rows: FinanceRow[];
  disclosure: string;
};

export const FINANCE_HUB_DESCRIPTION =
  "Compare credit cards, crypto exchange fees and stock broker commissions — real fees, side by side, not marketing copy.";

const CREDIT_CARDS: FinancePageContent = {
  vertical: "credit-cards",
  path: "/finance/credit-cards",
  navLabel: "Credit Cards",
  eyebrow: "Finance · Credit Cards",
  title: "Know the Real Cost",
  subhead:
    "Annual fees, FX spreads, welcome bonuses with conditions attached — the numbers issuers don't lead with in the ad. We line them up side by side.",
  matchTitle: "Which card fits you?",
  matchQuestion: {
    prompt: "How do you spend most?",
    options: ["Groceries & gas", "Travel & flights", "Carry a balance"],
  },
  compareTitle: "Or compare every card yourself",
  compareSubhead:
    "Annual fees, rewards rates and welcome bonuses from Canadian issuers.",
  searchPlaceholder: "Search cards by name or issuer…",
  filters: ["All cards", "No annual fee", "Travel rewards", "Cash back", "Balance transfer"],
  columns: [
    { key: "fee", label: "Annual fee" },
    { key: "rewards", label: "Rewards rate" },
    { key: "bonus", label: "Welcome bonus" },
  ],
  rows: [
    {
      id: "placeholder-a",
      name: "[Issuer A] Rewards Card",
      initial: "A",
      values: { fee: "[$0–120]", rewards: "[1–5]%", bonus: "Up to [$XXX]" },
      bestFor: "Everyday spending",
      ctaLabel: "Apply",
    },
    {
      id: "placeholder-b",
      name: "[Issuer B] Travel Card",
      initial: "B",
      values: { fee: "[$120–150]", rewards: "[1.5–3]x pts", bonus: "[XX,XXX] pts" },
      bestFor: "Travel",
      ctaLabel: "Apply",
    },
    {
      id: "placeholder-c",
      name: "[Issuer C] Cash Back",
      initial: "C",
      values: { fee: "$0", rewards: "[0.5–2]%", bonus: "[$XX] bonus" },
      bestFor: "No-fee cash back",
      ctaLabel: "Apply",
    },
    {
      id: "placeholder-d",
      name: "[Issuer D] Business Card",
      initial: "D",
      values: { fee: "[$99–199]", rewards: "[1–2]%", bonus: "[$XXX] credit" },
      bestFor: "Small business",
      ctaLabel: "Apply",
    },
  ],
  disclosure:
    "Compensation from card issuers may impact how and where offers appear on this page. This site does not include all available offers.",
};

const CRYPTO: FinancePageContent = {
  vertical: "crypto",
  path: "/finance/crypto",
  navLabel: "Crypto Exchanges",
  eyebrow: "Finance · Crypto Exchanges",
  title: "Know the Real Cost",
  subhead:
    "Maker/taker percentages, withdrawal costs, deposit fees — the numbers that live in a fee-schedule PDF, not the app. We line them up side by side.",
  matchTitle: "Which exchange fits you?",
  matchQuestion: {
    prompt: "How do you trade?",
    options: ["Buy & hold occasionally", "Active day trading", "Large monthly volume"],
  },
  compareTitle: "Or compare every exchange yourself",
  compareSubhead:
    "Maker/taker fees, withdrawal costs and deposit fees across major exchanges.",
  searchPlaceholder: "Search exchanges by name…",
  filters: [
    "All exchanges",
    "Lowest fees",
    "Beginner friendly",
    "Advanced trading tools",
    "Canadian regulated",
  ],
  columns: [
    { key: "maker", label: "Maker fee" },
    { key: "taker", label: "Taker fee" },
    { key: "withdrawal", label: "Withdrawal" },
  ],
  rows: [
    {
      id: "placeholder-a",
      name: "[Exchange A]",
      initial: "A",
      values: { maker: "[0–0.1]%", taker: "[0.1–0.5]%", withdrawal: "[Network fee]" },
      bestFor: "Active trading",
      ctaLabel: "Trade",
    },
    {
      id: "placeholder-b",
      name: "[Exchange B]",
      initial: "B",
      values: { maker: "[0.1]%", taker: "[0.1]%", withdrawal: "[$0 + network]" },
      bestFor: "Beginners",
      ctaLabel: "Trade",
    },
    {
      id: "placeholder-c",
      name: "[Exchange C]",
      initial: "C",
      values: { maker: "0%", taker: "[0.04–0.1]%", withdrawal: "[Network fee]" },
      bestFor: "Large volume",
      ctaLabel: "Trade",
    },
    {
      id: "placeholder-d",
      name: "[Exchange D]",
      initial: "D",
      values: { maker: "[0.16]%", taker: "[0.26]%", withdrawal: "[Varies by coin]" },
      bestFor: "Canadian users",
      ctaLabel: "Trade",
    },
  ],
  disclosure:
    "Compensation from exchanges may impact how and where offers appear on this page. Fee tiers shown assume the lowest volume bracket — your actual rate may differ. Not investment advice.",
};

const BROKERS: FinancePageContent = {
  vertical: "brokers",
  path: "/finance/brokers",
  navLabel: "Stock Brokers",
  eyebrow: "Finance · Stock Brokers",
  title: "Know the Real Cost",
  subhead:
    "Trading commissions, account minimums, FX conversion spreads — the costs that quietly erode returns over years. We line them up side by side.",
  matchTitle: "Which broker fits you?",
  matchQuestion: {
    prompt: "How do you invest?",
    options: ["Buy & hold long-term", "Active trader", "New investor"],
  },
  compareTitle: "Or compare every broker yourself",
  compareSubhead: "Trading commissions, account fees and FX costs from Canadian brokers.",
  searchPlaceholder: "Search brokers by name…",
  filters: [
    "All brokers",
    "No commission",
    "Best for beginners",
    "Best for active trading",
    "Self-directed",
  ],
  columns: [
    { key: "commission", label: "Trading commission" },
    { key: "accountFee", label: "Account fee" },
    { key: "fxFee", label: "FX fee" },
  ],
  rows: [
    {
      id: "placeholder-a",
      name: "[Broker A]",
      initial: "A",
      values: { commission: "[$0–9.95]/trade", accountFee: "$0*", fxFee: "[1.5–2]%" },
      bestFor: "Beginners",
      ctaLabel: "Open account",
    },
    {
      id: "placeholder-b",
      name: "[Broker B]",
      initial: "B",
      values: { commission: "$0", accountFee: "$0", fxFee: "[1.5]%" },
      bestFor: "Long-term investing",
      ctaLabel: "Open account",
    },
    {
      id: "placeholder-c",
      name: "[Broker C]",
      initial: "C",
      values: { commission: "[$1–7 USD]/trade", accountFee: "[Tiered]", fxFee: "[Varies]" },
      bestFor: "Active trading",
      ctaLabel: "Open account",
    },
    {
      id: "placeholder-d",
      name: "[Broker D]",
      initial: "D",
      values: { commission: "[$4.95–9.95]/trade", accountFee: "$0", fxFee: "[1.5–2]%" },
      bestFor: "Margin & options",
      ctaLabel: "Open account",
    },
  ],
  disclosure:
    "Compensation from brokers may impact how and where offers appear on this page. This is not investment advice — consider your own financial situation before opening an account. *Some account fees are waived above a minimum balance.",
};

export const FINANCE_PAGES: Record<FinanceVertical, FinancePageContent> = {
  "credit-cards": CREDIT_CARDS,
  crypto: CRYPTO,
  brokers: BROKERS,
};

export const FINANCE_HUB_ITEMS: {
  vertical: FinanceVertical;
  title: string;
  description: string;
  isNew: boolean;
}[] = [
  {
    vertical: "credit-cards",
    title: "Credit Cards",
    description: "Annual fees, rewards rates & welcome bonuses from Canadian issuers.",
    isNew: false,
  },
  {
    vertical: "crypto",
    title: "Crypto Exchanges",
    description: "Maker/taker fees and withdrawal costs across major exchanges.",
    isNew: true,
  },
  {
    vertical: "brokers",
    title: "Stock Brokers",
    description: "Trading commissions, account fees and FX costs, compared.",
    isNew: true,
  },
];
