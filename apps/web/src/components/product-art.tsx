import type { ReactNode } from "react";

/**
 * Flat illustrations standing in for product photos. Amazon's own images may
 * only come from its API (see `ProductImage`), which the account can't use yet,
 * so every product gets a drawing of its *kind* — a pair of headphones, a
 * skillet — picked from the title, or failing that from its category. They are
 * inline SVG: a few hundred bytes each, no extra request.
 */

const INK = "#22365a";
const MID = "#5b7fb5";
const SOFT = "#c9dbf3";
const PALE = "#eaf2fc";
const HOT = "#f97316";
const TEAL = "#0f766e";
const WHITE = "#ffffff";

const ART: Record<string, ReactNode> = {
  headphones: (
    <>
      <path d="M14 38v-8a18 18 0 0 1 36 0v8" fill="none" stroke={INK} strokeWidth="4" />
      <rect x="9" y="34" width="11" height="18" rx="5" fill={MID} />
      <rect x="44" y="34" width="11" height="18" rx="5" fill={MID} />
      <rect x="12" y="38" width="5" height="10" rx="2.5" fill={SOFT} />
      <rect x="47" y="38" width="5" height="10" rx="2.5" fill={SOFT} />
    </>
  ),
  speaker: (
    <>
      <rect x="16" y="8" width="32" height="48" rx="8" fill={INK} />
      <circle cx="32" cy="40" r="10" fill={MID} />
      <circle cx="32" cy="40" r="4" fill={SOFT} />
      <circle cx="32" cy="19" r="4.5" fill={MID} />
    </>
  ),
  cable: (
    <>
      <path d="M20 14v14a12 12 0 0 0 24 0V14" fill="none" stroke={MID} strokeWidth="4" strokeLinecap="round" />
      <rect x="14" y="6" width="12" height="12" rx="3" fill={INK} />
      <rect x="38" y="6" width="12" height="12" rx="3" fill={INK} />
      <path d="M32 40v14" stroke={MID} strokeWidth="4" strokeLinecap="round" />
      <rect x="27" y="50" width="10" height="8" rx="2.5" fill={HOT} />
    </>
  ),
  mouse: (
    <>
      <rect x="19" y="8" width="26" height="48" rx="13" fill={INK} />
      <path d="M32 8v18" stroke={SOFT} strokeWidth="2" />
      <rect x="29.5" y="15" width="5" height="9" rx="2.5" fill={HOT} />
      <path d="M19 26h26" stroke={MID} strokeWidth="2" />
    </>
  ),
  keyboard: (
    <>
      <rect x="6" y="20" width="52" height="26" rx="5" fill={INK} />
      <g fill={SOFT}>
        <rect x="11" y="25" width="6" height="5" rx="1.2" />
        <rect x="20" y="25" width="6" height="5" rx="1.2" />
        <rect x="29" y="25" width="6" height="5" rx="1.2" />
        <rect x="38" y="25" width="6" height="5" rx="1.2" />
        <rect x="47" y="25" width="6" height="5" rx="1.2" />
        <rect x="11" y="33" width="6" height="5" rx="1.2" />
        <rect x="47" y="33" width="6" height="5" rx="1.2" />
      </g>
      <rect x="20" y="33" width="24" height="5" rx="1.2" fill={MID} />
    </>
  ),
  monitor: (
    <>
      <rect x="7" y="10" width="50" height="32" rx="4" fill={INK} />
      <rect x="11" y="14" width="42" height="24" rx="2" fill={SOFT} />
      <path d="M15 32l8-7 6 4 9-10 10 7" fill="none" stroke={MID} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="28" y="42" width="8" height="8" fill={MID} />
      <rect x="20" y="50" width="24" height="4" rx="2" fill={INK} />
    </>
  ),
  battery: (
    <>
      <rect x="27" y="6" width="10" height="6" rx="2" fill={MID} />
      <rect x="20" y="11" width="24" height="46" rx="6" fill={INK} />
      <rect x="20" y="11" width="24" height="15" rx="6" fill={HOT} />
      <path d="M34 30l-7 10h6l-3 9 8-11h-6z" fill={WHITE} />
    </>
  ),
  powerbank: (
    <>
      <rect x="14" y="10" width="36" height="44" rx="7" fill={INK} />
      <rect x="20" y="17" width="24" height="5" rx="2.5" fill={MID} />
      <g fill={SOFT}>
        <circle cx="24" cy="46" r="2" />
        <circle cx="30" cy="46" r="2" />
        <circle cx="36" cy="46" r="2" />
      </g>
      <circle cx="42" cy="46" r="2" fill={HOT} />
    </>
  ),
  vacuum: (
    <>
      <path d="M40 8L24 46" stroke={INK} strokeWidth="5" strokeLinecap="round" />
      <rect x="34" y="6" width="14" height="16" rx="6" fill={MID} transform="rotate(22 41 14)" />
      <path d="M8 56h30l-4-11H14z" fill={INK} />
      <rect x="8" y="53" width="30" height="5" rx="2.5" fill={HOT} />
    </>
  ),
  robotvac: (
    <>
      <ellipse cx="32" cy="36" rx="24" ry="17" fill={INK} />
      <ellipse cx="32" cy="32" rx="24" ry="16" fill={MID} />
      <circle cx="32" cy="32" r="7" fill={SOFT} />
      <circle cx="32" cy="32" r="3" fill={HOT} />
    </>
  ),
  pan: (
    <>
      <ellipse cx="26" cy="36" rx="20" ry="13" fill={INK} />
      <ellipse cx="26" cy="33" rx="16" ry="9" fill={MID} />
      <rect x="42" y="31" width="20" height="6" rx="3" fill={INK} />
    </>
  ),
  pot: (
    <>
      <rect x="12" y="24" width="40" height="28" rx="6" fill={MID} />
      <rect x="8" y="20" width="48" height="7" rx="3.5" fill={INK} />
      <rect x="27" y="12" width="10" height="7" rx="3" fill={INK} />
      <rect x="4" y="30" width="8" height="6" rx="3" fill={INK} />
      <rect x="52" y="30" width="8" height="6" rx="3" fill={INK} />
    </>
  ),
  pitcher: (
    <>
      <path d="M16 12h26l-3 42H19z" fill={SOFT} />
      <path d="M17.5 30h23l-1.5 24H19z" fill={MID} />
      <path d="M42 18h6a6 6 0 0 1 6 6v10a6 6 0 0 1-6 6h-7" fill="none" stroke={INK} strokeWidth="4" />
      <rect x="14" y="8" width="30" height="6" rx="3" fill={INK} />
    </>
  ),
  cup: (
    <>
      <path d="M14 16h30v26a10 10 0 0 1-10 10H24a10 10 0 0 1-10-10z" fill={MID} />
      <path d="M44 22h4a7 7 0 0 1 0 14h-4" fill="none" stroke={INK} strokeWidth="4" />
      <path d="M20 26h18M20 34h12" stroke={WHITE} strokeWidth="2.5" strokeLinecap="round" />
      <rect x="12" y="52" width="34" height="4" rx="2" fill={INK} />
    </>
  ),
  bricks: (
    <>
      <rect x="8" y="34" width="26" height="18" rx="3" fill={HOT} />
      <rect x="30" y="18" width="26" height="18" rx="3" fill={MID} />
      <rect x="34" y="34" width="22" height="18" rx="3" fill={INK} />
      <g fill={HOT}>
        <rect x="13" y="29" width="6" height="6" rx="2" />
        <rect x="23" y="29" width="6" height="6" rx="2" />
      </g>
      <g fill={MID}>
        <rect x="35" y="13" width="6" height="6" rx="2" />
        <rect x="45" y="13" width="6" height="6" rx="2" />
      </g>
    </>
  ),
  gamepad: (
    <>
      <path d="M16 20h32a12 12 0 0 1 12 12v6a9 9 0 0 1-17 4l-2-4H23l-2 4a9 9 0 0 1-17-4v-6a12 12 0 0 1 12-12z" fill={MID} />
      <path d="M18 27v10M13 32h10" stroke={WHITE} strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="43" cy="29" r="3" fill={HOT} />
      <circle cx="49" cy="35" r="3" fill={INK} />
    </>
  ),
  pencil: (
    <>
      <path d="M46 8l10 10-30 30-13 3 3-13z" fill={HOT} />
      <path d="M16 38l10 10-13 3z" fill={SOFT} />
      <path d="M13 51l3.5-1-2.5-2.5z" fill={INK} />
      <path d="M41 13l10 10" stroke={INK} strokeWidth="3" />
      <path d="M46 8l10 10-4 4-10-10z" fill={MID} />
    </>
  ),
  notes: (
    <>
      <rect x="10" y="12" width="36" height="36" rx="3" fill={SOFT} transform="rotate(-8 28 30)" />
      <rect x="18" y="16" width="36" height="36" rx="3" fill="#ffd66b" />
      <path d="M54 40v9a3 3 0 0 1-3 3h-9z" fill={HOT} />
      <path d="M24 26h22M24 33h22M24 40h12" stroke={INK} strokeWidth="2.5" strokeLinecap="round" />
    </>
  ),
  tape: (
    <>
      <circle cx="28" cy="32" r="20" fill={MID} />
      <circle cx="28" cy="32" r="9" fill={PALE} stroke={INK} strokeWidth="3" />
      <path d="M28 52h28v-8H46" fill={SOFT} />
      <path d="M52 52l4-8" stroke={INK} strokeWidth="2" />
    </>
  ),
  glue: (
    <>
      <path d="M27 6h10l2 12H25z" fill={HOT} />
      <rect x="20" y="18" width="24" height="38" rx="5" fill={INK} />
      <rect x="20" y="28" width="24" height="16" fill={MID} />
      <path d="M26 36h12" stroke={WHITE} strokeWidth="3" strokeLinecap="round" />
    </>
  ),
  wrench: (
    <>
      <path d="M44 8a12 12 0 0 0-11 17L10 48a5 5 0 0 0 7 7l23-23a12 12 0 0 0 16-14l-8 8-7-2-2-7 8-8a12 12 0 0 0-3-1z" fill={MID} />
      <circle cx="14" cy="51" r="2.5" fill={WHITE} />
    </>
  ),
  bulb: (
    <>
      <path d="M32 6a17 17 0 0 0-10 31c2 2 3 4 3 7h14c0-3 1-5 3-7A17 17 0 0 0 32 6z" fill="#ffd66b" />
      <rect x="25" y="44" width="14" height="5" rx="2" fill={INK} />
      <rect x="27" y="50" width="10" height="5" rx="2.5" fill={MID} />
      <path d="M27 26l5 6 5-6" fill="none" stroke={HOT} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  chair: (
    <>
      <path d="M16 14l6 22h22l6-22" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 22h24l-3 13H23z" fill={MID} />
      <path d="M22 36l-8 20M42 36l8 20M24 36l20 20M40 36L20 56" stroke={INK} strokeWidth="3" strokeLinecap="round" />
    </>
  ),
  tent: (
    <>
      <path d="M32 10L6 52h52z" fill={TEAL} />
      <path d="M32 10l10 42H22z" fill={MID} />
      <path d="M32 30l6 22H26z" fill={INK} />
      <rect x="4" y="51" width="56" height="4" rx="2" fill={INK} />
    </>
  ),
  jar: (
    <>
      <rect x="15" y="10" width="34" height="11" rx="3" fill={INK} />
      <rect x="12" y="20" width="40" height="34" rx="7" fill={SOFT} />
      <rect x="12" y="30" width="40" height="14" fill={MID} />
      <path d="M22 37h20" stroke={WHITE} strokeWidth="3" strokeLinecap="round" />
    </>
  ),
  bottle: (
    <>
      <rect x="27" y="6" width="10" height="9" rx="2" fill={INK} />
      <path d="M24 15h16l3 9v28a5 5 0 0 1-5 5H26a5 5 0 0 1-5-5V24z" fill={SOFT} />
      <rect x="21" y="31" width="22" height="15" fill={MID} />
      <path d="M26 38.5h12" stroke={WHITE} strokeWidth="3" strokeLinecap="round" />
    </>
  ),
  toothbrush: (
    <>
      <rect x="29" y="22" width="7" height="36" rx="3.5" fill={MID} />
      <rect x="27" y="6" width="11" height="18" rx="4" fill={INK} />
      <g stroke={SOFT} strokeWidth="2" strokeLinecap="round">
        <path d="M27 10h-5M27 14h-5M27 18h-5" />
      </g>
      <rect x="29" y="40" width="7" height="6" fill={HOT} />
    </>
  ),
  bone: (
    <>
      <rect x="18" y="27" width="28" height="10" fill={SOFT} transform="rotate(-25 32 32)" />
      <g fill={SOFT}>
        <circle cx="16" cy="34" r="6.5" />
        <circle cx="20" cy="43" r="6.5" />
        <circle cx="44" cy="21" r="6.5" />
        <circle cx="48" cy="30" r="6.5" />
      </g>
      <path d="M24 37l16-8" stroke={MID} strokeWidth="2.5" strokeLinecap="round" />
    </>
  ),
  babybottle: (
    <>
      <path d="M28 6h8l3 8H25z" fill={HOT} />
      <rect x="22" y="14" width="20" height="6" rx="2" fill={INK} />
      <rect x="23" y="20" width="18" height="36" rx="6" fill={SOFT} />
      <rect x="23" y="34" width="18" height="22" rx="6" fill={MID} />
      <path d="M36 28h5M36 34h5M36 40h5" stroke={INK} strokeWidth="2" />
    </>
  ),
  towel: (
    <>
      <rect x="10" y="14" width="44" height="36" rx="5" fill={SOFT} />
      <rect x="10" y="14" width="44" height="12" rx="5" fill={MID} />
      <path d="M10 40h44" stroke={WHITE} strokeWidth="3" />
      <path d="M16 50v5M24 50v5M32 50v5M40 50v5M48 50v5" stroke={MID} strokeWidth="2.5" strokeLinecap="round" />
    </>
  ),
  plug: (
    <>
      <path d="M24 6v12M40 6v12" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <path d="M16 18h32v10a16 16 0 0 1-32 0z" fill={MID} />
      <path d="M32 44v14" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <path d="M34 22l-6 8h5l-2 7 7-9h-5z" fill={WHITE} />
    </>
  ),
  box: (
    <>
      <path d="M32 8l22 10v26L32 56 10 44V18z" fill={SOFT} />
      <path d="M32 30v26L10 44V18z" fill={MID} />
      <path d="M32 30l22-12" stroke={INK} strokeWidth="2.5" />
      <path d="M32 30L10 18" stroke={INK} strokeWidth="2.5" />
      <path d="M21 13l22 10v8" fill="none" stroke={HOT} strokeWidth="3" />
    </>
  ),
};

/** First match wins, so the specific product kinds come before the broad ones. */
const BY_TITLE: [RegExp, keyof typeof ART][] = [
  [/headphone|earbud|earphone|headset/, "headphones"],
  [/speaker|echo dot|soundbar/, "speaker"],
  [/robot vacuum|robovac/, "robotvac"],
  [/vacuum|steam mop/, "vacuum"],
  [/monitor|television|\btv\b/, "monitor"],
  [/keyboard/, "keyboard"],
  [/\bmouse\b/, "mouse"],
  [/power bank|portable charger/, "powerbank"],
  [/batter(y|ies)/, "battery"],
  [/cable|charger|adapter|smart plug|outlet|surge|\bups\b|extension cord/, "plug"],
  [/skillet|frying pan|\bpan\b|griddle/, "pan"],
  [/pitcher|water bottle|tumbler|thermos|kettle/, "pitcher"],
  [/french press|coffee|measuring cup|\bmug\b/, "cup"],
  [/lego|building toy|\bbricks?\b/, "bricks"],
  [/crayon|pencil|\bpens?\b|marker|highlighter/, "pencil"],
  [/post-it|sticky note|notebook/, "notes"],
  [/tape measure|wrench|screwdriver|\bdrill|plier|hammer/, "wrench"],
  [/\btape\b/, "tape"],
  [/glue|wd-40|lubricant|sealant/, "glue"],
  [/bulb|\bled\b|\blamp\b|\blights?\b/, "bulb"],
  [/chair|cooler/, "chair"],
  [/toothbrush|toothpaste|floss/, "toothbrush"],
  [/serum|cleanser|lotion|shampoo|mouthwash|face wash/, "bottle"],
  [/cream|moisturi|ointment|sunscreen/, "jar"],
  [/\bdogs?\b|\bcats?\b|\bpets?\b|kong|chuckit|furminator/, "bone"],
  [/pacifier|diaper|\bbaby\b|wipes/, "babybottle"],
  [/towel|\bcloths?\b|\bmat\b/, "towel"],
];

const BY_CATEGORY: Record<string, keyof typeof ART> = {
  electronics: "plug",
  home: "bulb",
  kitchen: "pot",
  baby: "babybottle",
  office: "notes",
  "personal-care": "jar",
  beauty: "jar",
  health: "jar",
  "pet-supplies": "bone",
  pets: "bone",
  "sports-outdoors": "tent",
  tools: "wrench",
  "toys-games": "gamepad",
  // Guides without a product in the title get the chart-on-a-screen drawing.
  guide: "monitor",
};

export function artKeyFor(title: string | null | undefined, categorySlug?: string | null): string {
  const text = (title ?? "").toLowerCase();
  if (text) {
    for (const [pattern, key] of BY_TITLE) {
      if (pattern.test(text)) return key;
    }
  }
  return (categorySlug && BY_CATEGORY[categorySlug]) || "box";
}

export function ProductArt({
  title,
  categorySlug,
  size = "card",
}: {
  title?: string | null;
  categorySlug?: string | null;
  size?: "card" | "tile" | "hero";
}) {
  const key = artKeyFor(title, categorySlug);
  return (
    <span className={`product-art product-art-${size}`} aria-hidden="true">
      <svg viewBox="0 0 64 64" focusable="false">
        {ART[key] ?? ART.box}
      </svg>
    </span>
  );
}

/** A small maple leaf for the "in Canada" tagline. */
export function MapleLeaf({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" className={className} focusable="false" viewBox="0 0 24 24">
      <path
        d="M12 1.5l2.1 4.2 2.6-1.3-.9 5.2 3-2.4.8 2.7 3-.5-1.7 3.7 2 1.2-5.2 3.6.7 2.3-5.4-.9V23h-2v-3.7l-5.4.9.7-2.3L1.1 14.3l2-1.2-1.7-3.7 3 .5.8-2.7 3 2.4-.9-5.2 2.6 1.3z"
        fill="#e11d2e"
      />
    </svg>
  );
}
