import { describe, expect, it } from "vitest";

import { ANONYMOUS_USER_STORAGE_KEY, getOrCreateAnonymousUserId } from "./anonymous-user";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem(key: string) {
      return data.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      data.set(key, value);
    },
    snapshot() {
      return Object.fromEntries(data);
    },
  };
}

describe("getOrCreateAnonymousUserId", () => {
  it("reuses a stored opaque id", () => {
    const storage = memoryStorage({
      [ANONYMOUS_USER_STORAGE_KEY]: "anon_ExistingUserIdValue",
    });

    expect(getOrCreateAnonymousUserId(storage)).toBe("anon_ExistingUserIdValue");
  });

  it("creates and persists an opaque id without long digit runs", () => {
    const storage = memoryStorage();
    const first = getOrCreateAnonymousUserId(storage);
    const second = getOrCreateAnonymousUserId(storage);

    expect(first).toMatch(/^anon_[A-Za-z]{18}$/);
    expect(first).toBe(second);
    expect(/\d{7,}/.test(first)).toBe(false);
    expect(storage.snapshot()[ANONYMOUS_USER_STORAGE_KEY]).toBe(first);
  });
});
