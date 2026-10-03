/**
 * Homepage hero illustration: a laptop showing a 90-day price line that ends
 * in a drop, with a "Buy" tag — the product in one picture. Inline SVG.
 */
export function HeroArt() {
  return (
    <svg className="hp-hero-svg" viewBox="0 0 420 300" focusable="false">
      <ellipse cx="210" cy="268" rx="190" ry="18" fill="#e3ecf8" />
      {/* screen */}
      <rect x="70" y="36" width="280" height="186" rx="14" fill="#22365a" />
      <rect x="84" y="50" width="252" height="158" rx="6" fill="#ffffff" />
      {/* chart grid */}
      <g stroke="#e3ecf8" strokeWidth="2">
        <path d="M100 96h220M100 132h220M100 168h220" />
      </g>
      {/* 90-day band */}
      <rect x="100" y="86" width="220" height="10" rx="5" fill="#fde4d3" />
      <rect x="100" y="176" width="220" height="10" rx="5" fill="#d6f1ec" />
      {/* price line */}
      <path
        d="M104 116l26-10 24 16 26-22 24 12 24-14 26 30 22 34 22 14"
        fill="none"
        stroke="#5b7fb5"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="298" cy="176" r="9" fill="#0f766e" stroke="#ffffff" strokeWidth="4" />
      {/* verdict tag */}
      <rect x="228" y="62" width="92" height="30" rx="15" fill="#0f766e" />
      <path d="M244 77l6 6 11-12" fill="none" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="270" y="72" width="38" height="9" rx="4.5" fill="#ffffff" />
      {/* base */}
      <path d="M40 232h340l-18 24H58z" fill="#5b7fb5" />
      <rect x="170" y="238" width="80" height="7" rx="3.5" fill="#c9dbf3" />
      {/* price tag */}
      <g transform="rotate(-14 78 96)">
        <path d="M34 78h58l22 20-22 20H34a8 8 0 0 1-8-8V86a8 8 0 0 1 8-8z" fill="#f97316" />
        <circle cx="92" cy="98" r="6" fill="#ffffff" />
        <rect x="38" y="90" width="34" height="6" rx="3" fill="#ffffff" />
        <rect x="38" y="101" width="22" height="6" rx="3" fill="#fde4d3" />
      </g>
    </svg>
  );
}
