import { getApiBaseUrl } from "@/lib/config";

// mirrors app/services/discovery/alternatives.py

export type AlternativeHit = {
  product_id: string;
  title: string;
  price_cents: number;
  currency: string;
  verdict: "BUY" | "FAIR";
  score: number;
  reason: string | null;
};

export type AlternativesResult = {
  reference_product_id: string;
  reference_price_cents: number;
  search_terms: string;
  alternatives: AlternativeHit[];
};

export async function requestAlternatives(
  productInput: string,
  fetchImpl: typeof fetch = fetch
): Promise<AlternativesResult | null> {
  const value = productInput.trim();
  const params = new URLSearchParams();
  if (/^[A-Za-z0-9]{10}$/.test(value)) params.set("product_id", value.toUpperCase());
  else params.set("url", value);
  try {
    const res = await fetchImpl(`/api/alternatives?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as AlternativesResult;
  } catch {
    return null;
  }
}

export async function fetchAlternativesByAsin(
  asin: string
): Promise<AlternativesResult | null> {
  try {
    const url = new URL("/alternatives", getApiBaseUrl());
    url.searchParams.set("product_id", asin.toUpperCase());
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return (await res.json()) as AlternativesResult;
  } catch {
    return null;
  }
}
