/**
 * LSTORAGE-02: Safe localStorage wrapper
 * - Guards against SSR (window undefined)
 * - LSTORAGE-03: Catches QuotaExceededError gracefully
 * - LSTORAGE-04: No schema versioning yet — reserved for future migration
 */

export function safeLocalStorageGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeLocalStorageSet(key: string, value: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (err) {
    if (err instanceof DOMException && err.name === "QuotaExceededError") {
      // LSTORAGE-03: Storage full — attempt to free space by removing oldest faultray keys
      console.warn("[storage] QuotaExceededError — clearing old simulation data");
      try {
        const keysToEvict = Object.keys(localStorage)
          .filter((k) => k.startsWith("faultray_") && k !== key)
          .slice(0, 3);
        keysToEvict.forEach((k) => localStorage.removeItem(k));
        localStorage.setItem(key, value);
        return true;
      } catch {
        return false;
      }
    }
    return false;
  }
}

export function safeLocalStorageRemove(key: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore
  }
}
