import Link from "next/link";

import { FINANCE_HUB_ITEMS, type FinancePageContent } from "@/lib/finance";

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  );
}

function SparkleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
    </svg>
  );
}

/** Cross-links between the three Finance verticals, shown on every /finance/* page. */
export function FinanceSubNav({ active }: { active: FinancePageContent["vertical"] }) {
  return (
    <nav className="finance-nav" aria-label="Finance sections">
      {FINANCE_HUB_ITEMS.map((item) => {
        const href = `/finance/${item.vertical}`;
        return (
          <Link key={item.vertical} href={href} aria-current={item.vertical === active ? "page" : undefined}>
            {item.title}
          </Link>
        );
      })}
    </nav>
  );
}

export function FinancePageBody({ content }: { content: FinancePageContent }) {
  return (
    <>
      <FinanceSubNav active={content.vertical} />

      <section className="finance-hero">
        <div>
          <p className="finance-eyebrow">{content.eyebrow}</p>
          <h1 className="finance-hero-title">{content.title}</h1>
          <p className="finance-hero-sub">{content.subhead}</p>
        </div>

        <div className="finance-match-card">
          <div className="finance-match-head">
            <span className="finance-match-icon" aria-hidden="true">
              <SparkleIcon />
            </span>
            <div>
              <p className="finance-match-title">{content.matchTitle}</p>
              <p className="finance-match-meta">3 questions · matched in 30 seconds</p>
            </div>
          </div>
          <div>
            <p className="finance-match-prompt">{content.matchQuestion.prompt}</p>
            <div className="finance-match-chips">
              {content.matchQuestion.options.map((option) => (
                <span className="finance-match-chip" key={option}>
                  {option}
                </span>
              ))}
            </div>
          </div>
          <button type="button" className="finance-match-cta" disabled>
            Start matching →
          </button>
          <p className="finance-match-note">Matching engine launching with real offers soon.</p>
        </div>
      </section>

      <div className="finance-compare-head">
        <div>
          <h2>{content.compareTitle}</h2>
          <p>{content.compareSubhead}</p>
        </div>
        <p className="finance-compare-note">
          Illustrative layout — sample data
          <br />
          for design review only
        </p>
      </div>

      <label className="finance-search">
        <SearchIcon />
        <span className="sr-only">{content.searchPlaceholder}</span>
        <input type="text" placeholder={content.searchPlaceholder} disabled />
      </label>

      <div className="finance-filters">
        {content.filters.map((filter) => (
          <span className="finance-filter-chip" key={filter}>
            {filter}
          </span>
        ))}
      </div>

      <div className="finance-table-wrap">
        <table className="finance-table">
          <thead>
            <tr>
              <th scope="col">{content.vertical === "crypto" ? "Exchange" : content.vertical === "brokers" ? "Broker" : "Card"}</th>
              {content.columns.map((column) => (
                <th scope="col" key={column.key}>
                  {column.label}
                </th>
              ))}
              <th scope="col">Best for</th>
              <th scope="col" aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {content.rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <span className="finance-table-name">
                    <span className="finance-table-avatar" aria-hidden="true">
                      {row.initial}
                    </span>
                    {row.name}
                  </span>
                </td>
                {content.columns.map((column) => (
                  <td key={column.key}>{row.values[column.key]}</td>
                ))}
                <td className="finance-table-best">{row.bestFor}</td>
                <td>
                  <span className="finance-table-cta" aria-disabled="true">
                    {row.ctaLabel}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="finance-disclosure">{content.disclosure}</p>
    </>
  );
}
