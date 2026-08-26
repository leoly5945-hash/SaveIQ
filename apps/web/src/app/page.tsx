import Link from "next/link";

import { getBrandName } from "@/lib/config";
import { HOME_AFFILIATE_DISCLOSURE } from "@/lib/home-recommendations";

import { HomeSearch } from "./home-search";

export default function Home() {
  const brandName = getBrandName();

  return (
    <main className="home-shell">
      <header className="home-topbar">
        <p className="brand-mark">{brandName}</p>
      </header>

      <h1 className="home-title">Find a better deal</h1>
      <HomeSearch />

      <footer className="home-footer">
        <p>{HOME_AFFILIATE_DISCLOSURE}</p>
        <p>
          <Link href="/privacy">Privacy</Link>
        </p>
      </footer>
    </main>
  );
}
