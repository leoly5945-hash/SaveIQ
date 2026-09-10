// mirrors app/services/discovery

export type ShoppingQuery = {
  raw: string;
  search_terms: string;
  price_min_cents: number | null;
  price_max_cents: number | null;
  parser_mode: string;
};

export type DiscoverHit = {
  product_id: string;
  title: string;
  brand: string | null;
  image_url: string | null;
  price_cents: number | null;
  currency: string;
  in_budget: boolean | null;
};

export type DiscoverResult = {
  query: ShoppingQuery;
  hits: DiscoverHit[];
  price_probed: boolean;
};

export type DiscoverOutcome =
  | { ok: true; result: DiscoverResult }
  | { ok: false; detail: string };

export async function requestDiscover(
  q: string,
  fetchImpl: typeof fetch = fetch
): Promise<DiscoverOutcome> {
  const params = new URLSearchParams({ q: q.trim() });
  try {
    const res = await fetchImpl(`/api/discover?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    const body = (await res.json()) as
      | DiscoverResult
      | { detail?: string | { msg?: string }[] };
    if (!res.ok) {
      const d = (body as { detail?: unknown }).detail;
      const detail =
        typeof d === "string"
          ? d
          : Array.isArray(d) && typeof d[0]?.msg === "string"
            ? (d[0].msg as string)
            : "Search failed. Try describing it differently.";
      return { ok: false, detail };
    }
    return { ok: true, result: body as DiscoverResult };
  } catch {
    return { ok: false, detail: "Couldn't reach search." };
  }
}
