import { getApiBaseUrl, getBrandName } from "@/lib/config";

export default function Home() {
  const apiBaseUrl = getApiBaseUrl();
  const brandName = getBrandName();

  return (
    <main className="app-shell">
      <section>
        <h1>{brandName} foundation</h1>
        <p className="lede">
          Modular monolith starter for the AI affiliate platform, with local
          health checks and infrastructure ready for the next product slice.
        </p>
      </section>

      <section className="status-panel" aria-labelledby="foundation-status">
        <h2 id="foundation-status">Foundation status</h2>
        <div className="status-grid">
          <div className="status-item">
            <p className="status-label">Frontend</p>
            <p className="status-value pill">Ready</p>
          </div>
          <div className="status-item">
            <p className="status-label">Backend API</p>
            <p className="status-value">{apiBaseUrl}</p>
          </div>
          <div className="status-item">
            <p className="status-label">Affiliate providers</p>
            <p className="status-value">Mock interface only</p>
          </div>
        </div>
      </section>
    </main>
  );
}
