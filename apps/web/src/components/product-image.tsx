import { ProductArt } from "@/components/product-art";
import { buyLinkRel } from "@/lib/config";

/**
 * Amazon's own product image when we hold one (Creators API), otherwise a
 * drawing of the product's kind. The image is served from Amazon's CDN and links to the Amazon
 * product page through our affiliate link, as the Associates licence expects.
 */
export function ProductImage({
  src,
  title,
  href,
  categorySlug,
  size = "card",
}: {
  src?: string | null;
  title: string;
  href?: string | null;
  categorySlug?: string | null;
  size?: "card" | "hero";
}) {
  if (!src) {
    return size === "card" ? <ProductArt categorySlug={categorySlug} title={title} /> : null;
  }
  const img = (
    // eslint-disable-next-line @next/next/no-img-element -- Amazon's CDN image, not ours to optimise or copy
    <img
      alt={title}
      className={`product-image product-image-${size}`}
      decoding="async"
      loading="lazy"
      src={src}
    />
  );
  if (!href) return img;
  return (
    <a
      aria-label={`${title} on Amazon.ca`}
      className="product-image-link"
      href={href}
      rel={buyLinkRel(href)}
      target="_blank"
    >
      {img}
    </a>
  );
}
