import crypto from "node:crypto";

export const SIGNATURE_HEADER = "x-otterprojects-signature";

/** `sha256=<hex hmac>` over the raw request body. */
export function signBody(body: string, secret: string): string {
  return `sha256=${crypto.createHmac("sha256", secret).update(body, "utf8").digest("hex")}`;
}

/** Constant-time verification of an `X-OtterProjects-Signature` header. */
export function verifySignature(body: string, header: string | null | undefined, secret: string): boolean {
  if (!header) return false;
  const expected = signBody(body, secret);
  const a = Buffer.from(header, "utf8");
  const b = Buffer.from(expected, "utf8");
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}
