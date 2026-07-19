import type { Metadata } from "next";
import "./globals.css";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

export const metadata: Metadata = {
  title: brandName,
  description: "AI-assisted affiliate deal discovery platform foundation.",
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
