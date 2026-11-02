import { formatBytes } from "./format.js";

const MAX_BYTES = 10 * 1024 * 1024;
const OPTIMISE_ABOVE_BYTES = 4 * 1024 * 1024;
const MAX_SIDE = 2048;
// The server rejects photos whose shorter side is under 200 px.
const MIN_SIDE = 200;
const EXTENSIONS = { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"] };
const ALL_EXTENSIONS = Object.values(EXTENSIONS).flat();

export class PhotoError extends Error {}

function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

function baseName(name) {
  const dot = name.lastIndexOf(".");
  return (dot > 0 ? name.slice(0, dot) : name) || "photo";
}

/** Pasted images often arrive without a usable file name; give them one that matches their type. */
export function nameForPastedImage(file) {
  const extensions = EXTENSIONS[file.type];
  if (!extensions || extensions.includes(extensionOf(file.name))) return file;
  return new File([file], `pasted-photo${extensions[0]}`, { type: file.type, lastModified: file.lastModified });
}

/**
 * Checks a chosen file and shrinks large photos before upload.
 * Resolves to { file, originalSize?, note? } or throws a PhotoError with a message for the user.
 */
export async function preparePhoto(file) {
  if (!(file.type in EXTENSIONS) || !ALL_EXTENSIONS.includes(extensionOf(file.name))) {
    throw new PhotoError("I can only check JPG, JPEG or PNG photos. Please choose a photo in one of those formats.");
  }

  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    if (file.size > MAX_BYTES) {
      throw new PhotoError("I couldn't open this photo to make it smaller, and it is larger than 10 MB. Please choose a different JPG or PNG photo.");
    }
    return { file, note: "No preview for this photo. It will be sent as it is." };
  }

  try {
    const longSide = Math.max(bitmap.width, bitmap.height);
    const shortSide = Math.min(bitmap.width, bitmap.height);
    if (shortSide < MIN_SIDE) {
      throw new PhotoError(
        `This photo is only ${bitmap.width} × ${bitmap.height} pixels. Please use one that is at least ${MIN_SIDE} × ${MIN_SIDE} pixels.`,
      );
    }
    if (longSide <= MAX_SIDE && file.size <= OPTIMISE_ABOVE_BYTES) return { file };

    // Shrink the long side to MAX_SIDE, but never push the short side under the server's minimum.
    const scale = Math.min(1, Math.max(MAX_SIDE / longSide, MIN_SIDE / shortSide));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.imageSmoothingQuality = "high";
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) throw new PhotoError("I couldn't make this photo smaller. Please choose a smaller JPG or PNG photo.");

    const optimized = new File([blob], `${baseName(file.name)}.jpg`, { type: "image/jpeg", lastModified: Date.now() });
    // Re-encoding a small, simple image can make it bigger; then the original is the better upload.
    if (optimized.size >= file.size && file.size <= MAX_BYTES) return { file };
    if (optimized.size > MAX_BYTES) {
      throw new PhotoError(`This photo is still ${formatBytes(optimized.size)} after optimizing, and the limit is 10 MB. Please choose a smaller photo.`);
    }
    return { file: optimized, originalSize: file.size };
  } finally {
    bitmap.close();
  }
}
