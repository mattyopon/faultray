/**
 * SEC: validate a post-auth `redirectTo` as a SAME-ORIGIN internal path.
 *
 * Used by both the login page and the OAuth callback so they agree on what is
 * accepted (previously the callback used a narrow hard-coded allow-list that
 * silently dropped valid deep links like `/people-risk/actions` to
 * `/dashboard`, while the login page accepted them — an inconsistency).
 *
 * The redirect target is always built same-origin (`${origin}${path}`), so any
 * internal path that passes these checks is safe from open-redirect. We reject:
 *   - non-strings / empty
 *   - any whitespace (a clean path has none; a literal space would be `%20`)
 *   - protocol-relative (`//host`) and backslash variants (browsers fold `\`→`/`,
 *     enabling `//host`)
 *   - path traversal (`..`), including percent-encoded (`%2e%2e`) and
 *     double-encoded (`%252e`) forms, and encoded backslash (`%5c`)
 *   - anything that doesn't resolve to the same origin
 */
export function isSafeInternalPath(raw: string | null | undefined): boolean {
  if (typeof raw !== "string" || raw.length === 0) return false;
  // No whitespace anywhere. A legitimate space in a query is percent-encoded
  // (`%20`); a raw space/tab/newline means the value isn't a clean path. This
  // also subsumes the old leading/trailing-trim check.
  if (/\s/.test(raw)) return false;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return false;
  if (raw.includes("\\") || raw.includes("..")) return false;
  // Defeat percent-encoded traversal / backslash (`/%2e%2e/admin`, `/%5cevil`).
  // `new URL` decodes and normalizes `%2e%2e` to `..`, so the literal check above
  // misses it. Decode repeatedly so double-encoding (`%252e` → `%2e` → `.`)
  // can't smuggle a segment past us, then re-inspect. Malformed encoding (a bare
  // `%`) makes decodeURIComponent throw — reject those too. We deliberately do
  // NOT reject decoded whitespace here so legitimate encoded-space query values
  // (e.g. `/search?q=a%20b`) still pass.
  let decoded = raw;
  try {
    for (let i = 0; i < 3; i++) {
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    }
  } catch {
    return false;
  }
  if (decoded.includes("\\") || decoded.includes("..")) return false;
  try {
    const base = "https://faultray.invalid";
    return new URL(raw, base).origin === base;
  } catch {
    return false;
  }
}
