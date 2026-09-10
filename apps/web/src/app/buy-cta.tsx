/**
 * The one link on a verdict card that pays us. Rendered twice — once near the
 * top of the card (`top`, with a gentle motion-safe pulse) and once at the
 * bottom after the analysis. Always the affiliate-tagged `buy_url`.
 */
export function BuyCta({ href, top = false }: { href: string; top?: boolean }) {
  return (
    <a
      className={top ? "verdict-cta verdict-cta-top" : "verdict-cta"}
      href={href}
      rel="sponsored nofollow noopener noreferrer"
      target="_blank"
    >
      Buy on Amazon.ca
      <span aria-hidden="true"> →</span>
    </a>
  );
}
