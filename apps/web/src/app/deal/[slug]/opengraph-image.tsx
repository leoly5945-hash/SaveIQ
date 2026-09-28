import { ImageResponse } from "next/og";

import {
  dealPriceNow,
  fetchDeal,
  formatMoney,
} from "@/lib/featured-deals";

export const alt = "SaveIQ price check";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Brand colours, matching globals.css (--accent-strong / --promo).
const TEAL = "#0b5d57";
const TEAL_DARK = "#083f3b";
const ORANGE = "#f97316";

export default async function Image({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const deal = await fetchDeal(slug);

  if (!deal) {
    return new ImageResponse(
      (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            height: "100%",
            background: TEAL,
            color: "#ffffff",
            fontSize: 64,
            fontWeight: 800,
          }}
        >
          SaveIQ
        </div>
      ),
      { ...size }
    );
  }

  const now = dealPriceNow(deal);
  const price = formatMoney(now.cents, now.currency);
  const checked = now.checked;

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          width: "100%",
          height: "100%",
          padding: 64,
          background: `linear-gradient(135deg, ${TEAL} 0%, ${TEAL_DARK} 100%)`,
          fontFamily: "sans-serif",
        }}
      >
        {/* Wordmark */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 64,
              height: 64,
              borderRadius: 18,
              background: "#ffffff",
              color: TEAL,
              fontSize: 30,
              fontWeight: 900,
            }}
          >
            iQ
          </div>
          <div style={{ display: "flex", fontSize: 40, fontWeight: 800, color: "#ffffff" }}>
            SaveIQ
          </div>
        </div>

        {/* Product + price */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div
            style={{
              display: "flex",
              fontSize: 52,
              fontWeight: 800,
              color: "#ffffff",
              lineHeight: 1.15,
              maxHeight: 220,
              overflow: "hidden",
            }}
          >
            {deal.title}
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
            <div style={{ display: "flex", fontSize: 72, fontWeight: 900, color: ORANGE }}>
              {price}
            </div>
            <div style={{ display: "flex", fontSize: 32, fontWeight: 600, color: "#d7f0ec" }}>
              at {deal.merchant}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 26,
            color: "#a9d8d2",
          }}
        >
          <div style={{ display: "flex" }}>
            {checked ? `Price checked ${checked}` : "Independent buying guides"}
          </div>
          <div style={{ display: "flex" }}>saveiq.ca</div>
        </div>
      </div>
    ),
    { ...size }
  );
}
