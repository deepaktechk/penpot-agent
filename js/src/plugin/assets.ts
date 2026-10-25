// Image uploads into the Penpot file, and the key -> ImageData registry used by image paints.
import { byId, runtime } from "./state";

/** base64 -> bytes */
export const b64 = (encoded: string): Uint8Array => {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
};

const BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** bytes -> base64, in plain JS (the plugin sandbox is not guaranteed to provide btoa). */
export const toBase64 = (bytes: Uint8Array): string => {
  const parts: string[] = [];
  for (let i = 0; i < bytes.length; i += 3) {
    const first = bytes[i], second = bytes[i + 1], third = bytes[i + 2];
    const triple = (first << 16) | ((second ?? 0) << 8) | (third ?? 0);
    parts.push(BASE64_ALPHABET[(triple >> 18) & 63] + BASE64_ALPHABET[(triple >> 12) & 63]
      + (second === undefined ? "=" : BASE64_ALPHABET[(triple >> 6) & 63]) + (third === undefined ? "=" : BASE64_ALPHABET[triple & 63]));
  }
  return parts.join("");
};

/** Export a shape with Penpot's exporter (png, jpeg, webp, svg, pdf at any scale) -> {name, base64}. */
export const exportShape = async (id: string, type: "png" | "jpeg" | "webp" | "svg" | "pdf" = "png", scale = 1): Promise<any> => {
  const shape = byId(id);
  if (!shape) throw new Error("shape not found: " + id);
  const bytes = await shape.export({ type, scale });
  return { id, name: shape.name, type, scale, base64: toBase64(bytes) };
};

/** CRC-32 (IEEE), same value as Python's zlib.crc32: detects corrupted transfers. */
export const crc32 = (bytes: Uint8Array): number => {
  let value: number, crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) {
    value = (crc ^ bytes[i]) & 0xFF;
    for (let bit = 0; bit < 8; bit++) value = value & 1 ? (value >>> 1) ^ 0xEDB88320 : value >>> 1;
    crc = (crc >>> 8) ^ value;
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
};

export const uploadB64 = async (key: string, data: string, mime?: string, crc?: number): Promise<any> => {
  const bytes = b64(data);
  if (crc !== undefined && crc32(bytes) !== crc) throw new Error("CRC mismatch for " + key);
  const image = await penpot.uploadMediaData(key, bytes, mime || "image/png");
  runtime.imgs[key] = image;
  return image;
};

/** Let Penpot's server fetch a public URL itself. */
export const uploadUrl = async (key: string, url: string): Promise<any> => {
  const image = await penpot.uploadMediaUrl(key, url);
  runtime.imgs[key] = image;
  return image;
};

/** Register known descriptors (after a re-injection); returns how many images are known. */
export const registerImages = (descriptors: Record<string, any>): number => {
  for (const [key, image] of Object.entries(descriptors)) runtime.imgs[key] = image;
  return Object.keys(runtime.imgs).length;
};
