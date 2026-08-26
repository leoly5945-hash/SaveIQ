export const ANONYMOUS_USER_STORAGE_KEY = "dealhunter.anonymous_user_id";

export type KvStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

const memoryStore = new Map<string, string>();

const memoryStorage: KvStorage = {
  getItem(key) {
    return memoryStore.get(key) ?? null;
  },
  setItem(key, value) {
    memoryStore.set(key, value);
  },
};

function defaultStorage(): KvStorage {
  if (typeof localStorage === "undefined") {
    return memoryStorage;
  }
  return localStorage;
}

function createAnonymousUserId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  const body = Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
  return `anon_${body}`;
}

function isUsableAnonymousId(value: string): boolean {
  return /^[A-Za-z0-9_-]{8,64}$/.test(value) && !/\d{7,}/.test(value);
}

export function getOrCreateAnonymousUserId(storage: KvStorage = defaultStorage()): string {
  const existing = storage.getItem(ANONYMOUS_USER_STORAGE_KEY)?.trim() ?? "";
  if (existing && isUsableAnonymousId(existing)) {
    return existing;
  }
  const created = createAnonymousUserId();
  storage.setItem(ANONYMOUS_USER_STORAGE_KEY, created);
  return created;
}
