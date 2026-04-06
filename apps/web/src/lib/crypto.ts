// Web Crypto API — compatible with Node.js 20+ and Vercel Edge Runtime

const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY;
if (!ENCRYPTION_KEY) {
  throw new Error("ENCRYPTION_KEY environment variable is not set");
}

const ENC_PREFIX = "ENC:";

async function getKey(): Promise<CryptoKey> {
  // Pad/truncate to exactly 32 bytes for AES-256
  const keyBytes = new TextEncoder().encode(
    ENCRYPTION_KEY.padEnd(32, "0").slice(0, 32)
  );
  return crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, [
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
