import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

import { getBrandName } from "@/lib/config";

const brandName = getBrandName();

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["700", "800", "900"],
  display: "swap",
  variable: "--font-archivo",
});

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
    <html lang="en" className={archivo.variable}>
      <body>{children}</body>
    </html>
  );
}
