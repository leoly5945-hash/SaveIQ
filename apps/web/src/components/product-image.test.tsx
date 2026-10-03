import { isValidElement, type ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { ProductArt } from "@/components/product-art";

import { ProductImage } from "./product-image";

const SRC = "https://m.media-amazon.com/images/I/41cNJGm9ZFL._SL500_.jpg";

type AnyProps = Record<string, unknown> & { children?: unknown };

describe("ProductImage", () => {
  it("falls back to a drawing of the product on a card when there is no image", () => {
    const el = ProductImage({ title: "KONG Classic", categorySlug: "pets" }) as ReactElement;
    expect(isValidElement(el)).toBe(true);
    expect(el.type).toBe(ProductArt);
  });

  it("renders nothing in the hero slot when there is no image", () => {
    expect(ProductImage({ title: "KONG Classic", size: "hero" })).toBeNull();
  });

  it("links the Amazon image to the affiliate URL as a sponsored link", () => {
    const el = ProductImage({
      src: SRC,
      title: "KONG Classic",
      href: "/go/12?t=affiliate",
    }) as ReactElement<AnyProps>;
    expect(el.type).toBe("a");
    expect(el.props.href).toBe("/go/12?t=affiliate");
    expect(String(el.props.rel)).toContain("sponsored");
    const img = el.props.children as ReactElement<AnyProps>;
    expect(img.type).toBe("img");
    expect(img.props.src).toBe(SRC);
    expect(img.props.alt).toBe("KONG Classic");
  });
});
