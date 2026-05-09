/**
 * Image upload helpers — validate file type/size and convert to base64
 * for the multimodal /chat request.
 */

import type { ChatImage, ImageMediaType } from "@/lib/types";

const SUPPORTED_TYPES: Record<string, ImageMediaType> = {
  "image/jpeg": "image/jpeg",
  "image/jpg": "image/jpeg",
  "image/png": "image/png",
  "image/webp": "image/webp",
  "image/gif": "image/gif",
};

/** ~5 MB raw — Anthropic's documented soft limit. */
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export interface PreparedImage {
  /** For sending to the backend. */
  payload: ChatImage;
  /** For previewing in the bubble (data URL form). */
  dataUrl: string;
}

export class ImageValidationError extends Error {}

/**
 * Read a `File` from an input/dropzone and produce both the base64 payload
 * we POST to /chat and the data URL we display as a preview.
 */
export async function prepareImage(file: File): Promise<PreparedImage> {
  const mediaType = SUPPORTED_TYPES[file.type.toLowerCase()];
  if (!mediaType) {
    throw new ImageValidationError(
      `Unsupported file type: ${file.type || "unknown"}. Use JPEG, PNG, WebP, or GIF.`,
    );
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new ImageValidationError(
      `Image is ${(file.size / 1024 / 1024).toFixed(1)} MB — over the ${(
        MAX_IMAGE_BYTES /
        1024 /
        1024
      ).toFixed(0)} MB limit.`,
    );
  }

  const dataUrl = await readAsDataUrl(file);
  // Strip the "data:image/png;base64," prefix — the backend wants raw base64.
  const commaIdx = dataUrl.indexOf(",");
  if (commaIdx === -1) {
    throw new ImageValidationError("Could not parse the image data — try a different file.");
  }
  const base64 = dataUrl.slice(commaIdx + 1);

  return {
    payload: { media_type: mediaType, base64_data: base64 },
    dataUrl,
  };
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new ImageValidationError("Could not read the image file."));
    reader.readAsDataURL(file);
  });
}
