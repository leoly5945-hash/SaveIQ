import type { ReactNode } from "react";

/**
 * A small line icon per Price Watch category, drawn inline — a stand-in for
 * product photos until we can use Amazon's own images through its API (the
 * Associates agreement only allows images from Amazon's approved tools).
 */
const PATHS: Record<string, ReactNode> = {
  baby: (
    <>
      <path d="M10 3h4M9.5 6h5l-.5-3h-4z" />
      <rect height="14" rx="3" width="8" x="8" y="6.5" />
      <path d="M8 11h3M8 14.5h3" />
    </>
  ),
  electronics: (
    <>
      <path d="M9 3v4M15 3v4" />
      <path d="M6.5 7h11v3.5a5.5 5.5 0 0 1-11 0z" />
      <path d="M12 16v5" />
    </>
  ),
  home: (
    <>
      <path d="M3.5 11 12 4l8.5 7" />
      <path d="M6 9.5V20h12V9.5" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  kitchen: (
    <>
      <circle cx="10" cy="13" r="6.5" />
      <path d="M16 11.5 21 9" />
      <path d="M8 13h.01" />
    </>
  ),
  office: (
    <>
      <path d="m15.5 4.5 4 4L9 19H5v-4z" />
      <path d="m13.5 6.5 4 4" />
    </>
  ),
  "personal-care": (
    <>
      <path d="M12 3.5c3 4 5.5 7 5.5 10a5.5 5.5 0 0 1-11 0c0-3 2.5-6 5.5-10z" />
      <path d="M9.5 14a2.5 2.5 0 0 0 2.5 2.5" />
    </>
  ),
  "pet-supplies": (
    <>
      <circle cx="7" cy="10" r="1.8" />
      <circle cx="10.5" cy="6.5" r="1.8" />
      <circle cx="14.5" cy="6.5" r="1.8" />
      <circle cx="18" cy="10" r="1.8" />
      <path d="M12.5 12c2.5 0 5 3.5 5 5.5 0 1.5-1.5 2.5-3 2-1-.3-1.5-.5-2-.5s-1 .2-2 .5c-1.5.5-3-.5-3-2 0-2 2.5-5.5 5-5.5z" />
    </>
  ),
  "sports-outdoors": (
    <>
      <path d="M3 20 12 5l9 15z" />
      <path d="M12 20v-6l-3 6M12 14l3 6" />
    </>
  ),
  tools: (
    <>
      <rect height="5" rx="1.5" width="11" x="3.5" y="4" />
      <path d="M14.5 5.2 19 3.5v6l-4.5-1.7" />
      <path d="M9 9v11" />
    </>
  ),
  "toys-games": (
    <>
      <rect height="15" rx="3" width="15" x="4.5" y="4.5" />
      <path d="M9 9h.01M15 9h.01M12 12h.01M9 15h.01M15 15h.01" />
    </>
  ),
};

const FALLBACK = (
  <>
    <path d="M3.5 12.5 11 5h8v8l-7.5 7.5a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8z" />
    <path d="M15 9h.01" />
  </>
);

export function CategoryIcon({ slug }: { slug: string | null }) {
  const icon =
    slug !== null && Object.prototype.hasOwnProperty.call(PATHS, slug)
      ? PATHS[slug]
      : null;
  return (
    <span
      aria-hidden="true"
      className={`category-icon category-icon-${icon ? slug : "other"}`}
    >
      <svg
        fill="none"
        height="24"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.9"
        viewBox="0 0 24 24"
        width="24"
      >
        {icon ?? FALLBACK}
      </svg>
    </span>
  );
}
