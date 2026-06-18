// Web Crypto API — compatible with Node.js 20+ and Vercel Edge Runtime

// #84 (P2): dev sentinel value を明示的に reject。.env.example の placeholder を
// そのまま production に渡すと AES-GCM が known key で全暗号化データ復号可能。
// 現在 crypto.ts は import 元なし (P0 ではない) だが、将来配線時に死なないよう
// 起動時 fail-fast する。
const DEV_SENTINEL_KEYS: ReadonlySet<string> = new Set([
  "faultray-dev-key-change-me",
  "change-me",
  "REPLACE_ME",
]);

function getEncryptionKey(): string {
  const key = process.env.ENCRYPTION_KEY;
  if (!key) {
    throw new Error("ENCRYPTION_KEY environment variable is not set");
  }
  if (DEV_SENTINEL_KEYS.has(key)) {
    throw new Error(
      "ENCRYPTION_KEY is set to a placeholder/dev value. " +
        "Generate a unique 32-byte secret (e.g. `openssl rand -hex 32`) before " +
        "encrypting any data."
    );
  }
  return key;
}

const ENC_PREFIX = "ENC:";

async function getKey(): Promise<CryptoKey> {
  // SEC (U15): derive a full-entropy 32-byte AES-256 key. The previous code did
  // `key.padEnd(32,"0").slice(0,32)`, which silently accepted short/low-entropy
  // secrets (zero-padded) and truncated/ignored hex/base64 encoding — quietly
  // destroying key strength. Require a sufficiently long secret and derive the
  // key via SHA-256 so the secret's full entropy is used and no key is silently
  // weakened. (This module has no callers yet, so the derivation change does not
  // affect any existing ciphertext.)
  const secret = getEncryptionKey();
  if (secret.length < 32) {
    throw new Error(
      "ENCRYPTION_KEY must be at least 32 characters (e.g. `openssl rand -hex 32`)."
    );
  }
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(secret)
  );
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, [
    "encrypt",
    "decrypt",
  ]);
}

export async function encrypt(text: string): Promise<string> {
  const key = await getKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const cipherBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(text)
  );
  // Combine iv (12 bytes) + ciphertext, encode as base64
  const combined = new Uint8Array(12 + cipherBuffer.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipherBuffer), 12);
  const base64 = btoa(String.fromCharCode(...combined));
  return `${ENC_PREFIX}${base64}`;
}

export async function decrypt(value: string): Promise<string> {
  // If not encrypted, return as-is (backward compatibility)
  if (!value.startsWith(ENC_PREFIX)) {
    return value;
  }
  const base64 = value.slice(ENC_PREFIX.length);
  const combined = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);
  const key = await getKey();
  const plainBuffer = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    key,
    ciphertext
  );
  return new TextDecoder().decode(plainBuffer);
}

/**
 * isEncrypted checks whether a value was encrypted by this module.
 * Use this when deciding whether to decrypt before display.
 */
export function isEncrypted(value: string): boolean {
  return value.startsWith(ENC_PREFIX);
}
