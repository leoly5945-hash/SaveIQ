/**
 * Large, well-known retailers selling to Canada. Only these may take the main
 * "Buy at …" button over Amazon. A cheaper offer from a store shoppers don't
 * know is still shown, but as a caveated secondary link: sending people to an
 * unvetted store with our loudest button is how a price tool loses trust.
 */
const TRUSTED = [
  "best buy",
  "walmart",
  "costco",
  "canadian tire",
  "staples",
  "the source",
  "home depot",
  "lowes",
  "rona",
  "newegg",
  "canada computers",
  "memory express",
  "visions electronics",
  "london drugs",
  "shoppers drug mart",
  "the brick",
  "leons",
  "sport chek",
  "mec",
  "indigo",
  "well ca",
  "real canadian superstore",
  "giant tiger",
  "hudsons bay",
  "the bay",
  "princess auto",
  "lee valley",
  "ikea",
  "apple",
  "samsung",
  "dell",
  "lenovo",
  "microsoft",
  "sony",
  "lg",
  "hp",
];

export function normalizeMerchant(name: string): string {
  let n = name
    .toLowerCase()
    .replace(/[’'`]/g, "")
    .replace(/^www\./, "")
    .replace(/\.(ca|com)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  // Drop only trailing qualifiers ("Best Buy Canada", "Apple Store"), never a
  // word that is part of the name ("Canada Computers").
  let prev = "";
  while (prev !== n) {
    prev = n;
    n = n.replace(/\s+(canada|store|official|online|ca)$/, "");
  }
  return n;
}

const compact = (s: string) => s.replace(/ /g, "");

export function isTrustedRetailer(name: string | null | undefined): boolean {
  if (!name) return false;
  const n = normalizeMerchant(name);
  // Compare with spaces removed too, so "BestBuy.ca" matches "best buy".
  return TRUSTED.some(
    (t) => n === t || n.startsWith(`${t} `) || compact(n) === compact(t)
  );
}
