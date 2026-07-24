// Classifies a file into the preview renderer it should use, based on its MIME
// type (with a filename-extension fallback for when the MIME type is missing or
// generic like `application/octet-stream`).

export type PreviewKind =
  | "image"
  | "video"
  | "audio"
  | "pdf"
  | "text"
  | "spreadsheet"
  | "word"
  | "presentation"
  | "unsupported";

const TEXT_MIME_TYPES = new Set([
  "application/json",
  "application/xml",
  "application/javascript",
  "application/typescript",
  "application/x-yaml",
  "application/yaml",
  "application/x-sh",
  "application/x-httpd-php",
  "application/sql",
]);

const EXT_KIND: Record<string, PreviewKind> = {
  // images
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image",
  bmp: "image", svg: "image", ico: "image",
  // video / audio
  mp4: "video", webm: "video", mov: "video", mkv: "video", avi: "video",
  mp3: "audio", wav: "audio", ogg: "audio", flac: "audio", m4a: "audio", aac: "audio",
  // documents
  pdf: "pdf",
  xlsx: "spreadsheet", xls: "spreadsheet",
  docx: "word",
  pptx: "presentation", ppt: "presentation",
  // text / code
  txt: "text", md: "text", markdown: "text", csv: "text", tsv: "text",
  json: "text", xml: "text", yaml: "text", yml: "text", html: "text", htm: "text",
  css: "text", js: "text", ts: "text", tsx: "text", jsx: "text", py: "text",
  rb: "text", go: "text", rs: "text", java: "text", kt: "text", c: "text",
  h: "text", cpp: "text", cs: "text", sh: "text", sql: "text", log: "text",
  toml: "text", ini: "text", env: "text",
};

function extensionOf(fileName: string): string {
  const idx = fileName.lastIndexOf(".");
  return idx >= 0 ? fileName.slice(idx + 1).toLowerCase() : "";
}

export function getPreviewKind(mimeType: string, fileName = ""): PreviewKind {
  const mime = (mimeType || "").toLowerCase();

  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime === "application/pdf") return "pdf";
  if (
    mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    mime === "application/vnd.ms-excel"
  )
    return "spreadsheet";
  if (mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return "word";
  if (
    mime === "application/vnd.openxmlformats-officedocument.presentationml.presentation" ||
    mime === "application/vnd.ms-powerpoint"
  )
    return "presentation";
  if (mime.startsWith("text/") || TEXT_MIME_TYPES.has(mime)) return "text";

  // MIME type absent or generic (e.g. application/octet-stream) — fall back to
  // the filename extension.
  if (!mime || mime === "application/octet-stream" || mime === "binary/octet-stream") {
    const kind = EXT_KIND[extensionOf(fileName)];
    if (kind) return kind;
  }

  return "unsupported";
}
