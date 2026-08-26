import type { Metadata } from "next";
import "./globals.css";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

export const metadata: Metadata = {
  title: brandName,
  description: "Find product deals and affiliate offers in Canada.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
