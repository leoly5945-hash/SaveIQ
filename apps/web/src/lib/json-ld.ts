/**
 * Serialize a JSON-LD object for a `<script type="application/ld+json">` tag.
 *
 * `JSON.stringify` does not escape `<`, so a value that ends up inside the
 * object — a product title pulled from Amazon/Keepa, say — can carry a literal
 * `</script>` and break out of the tag into the surrounding HTML. Escaping
 * every `<` as its Unicode form is the standard mitigation: it's invisible to
 * any JSON-LD consumer (Google, other structured-data parsers) but can no
 * longer close the tag early.
 */
export function safeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
