import { createElement } from "react";
import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

import { getBrandName, getSiteUrl } from "@/lib/config";

const brandName = getBrandName();

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["700", "800", "900"],
  display: "swap",
  variable: "--font-archivo",
});

export const metadata: Metadata = {
  metadataBase: new URL(getSiteUrl()),
  title: brandName,
  description: "Find product deals and affiliate offers in Canada.",
  alternates: { canonical: "/" },
};

// Site-verification <meta> tags. Impact.com's crawler reads the `value`
// attribute (not the standard `content`), so it can't go through Next's
// `metadata` API; React hoists this into <head>. One entry per Impact
// partner account that needs to verify this domain.
const SITE_VERIFICATION: { name: string; value: string }[] = [
  {
    name: "impact-site-verification",
    value: "8a1fefe4-3672-4a87-adb5-d4a2ae26f0a3",
  },
  {
    name: "impact-site-verification",
    value: "365bf15e-1e54-40c5-93ba-6faf851069c0",
  },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={archivo.variable}>
      <body>
        {SITE_VERIFICATION.map((tag) =>
          createElement("meta", { key: tag.value, name: tag.name, value: tag.value }),
        )}
        {children}
      </body>
    </html>
  );
}
