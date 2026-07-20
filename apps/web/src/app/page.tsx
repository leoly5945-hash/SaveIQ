import { getBrandName } from "@/lib/config";

import { SearchExperience } from "./search-experience";

export default function Home() {
  const brandName = getBrandName();

  return (
    <main className="app-shell">
      <header className="topbar">
        <p className="brand-mark">{brandName}</p>
        <p className="environment-note">Staging mock data only</p>
      </header>

      <SearchExperience searchEndpoint="/api/search" />
    </main>
  );
}
