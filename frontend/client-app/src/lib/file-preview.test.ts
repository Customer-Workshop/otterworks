import { describe, it, expect } from "vitest";
import { getPreviewKind } from "./file-preview";

describe("getPreviewKind", () => {
  it("classifies images by mime type (AC-02)", () => {
    expect(getPreviewKind("image/png", "a.png")).toBe("image");
    expect(getPreviewKind("image/jpeg", "a.jpg")).toBe("image");
  });

  it("classifies PDFs (AC-03)", () => {
    expect(getPreviewKind("application/pdf", "doc.pdf")).toBe("pdf");
  });

  it("classifies text/code/csv/markdown/json as text (AC-04)", () => {
    expect(getPreviewKind("text/plain", "a.txt")).toBe("text");
    expect(getPreviewKind("text/csv", "a.csv")).toBe("text");
    expect(getPreviewKind("text/markdown", "a.md")).toBe("text");
    expect(getPreviewKind("application/json", "a.json")).toBe("text");
    expect(getPreviewKind("application/xml", "a.xml")).toBe("text");
  });

  it("classifies spreadsheets (AC-05)", () => {
    expect(
      getPreviewKind(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "book.xlsx"
      )
    ).toBe("spreadsheet");
    expect(getPreviewKind("application/vnd.ms-excel", "old.xls")).toBe("spreadsheet");
  });

  it("classifies Word documents (AC-06)", () => {
    expect(
      getPreviewKind(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc.docx"
      )
    ).toBe("word");
  });

  it("classifies PowerPoint as presentation (AC-07)", () => {
    expect(
      getPreviewKind(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "deck.pptx"
      )
    ).toBe("presentation");
  });

  it("classifies audio and video (AC-08, AC-09)", () => {
    expect(getPreviewKind("audio/mpeg", "song.mp3")).toBe("audio");
    expect(getPreviewKind("video/mp4", "clip.mp4")).toBe("video");
  });

  it("falls back to unsupported for unknown types (AC-10)", () => {
    expect(getPreviewKind("application/zip", "archive.zip")).toBe("unsupported");
    expect(getPreviewKind("", "")).toBe("unsupported");
  });

  it("uses the filename extension when the mime type is generic octet-stream (AC-11)", () => {
    // LocalStack-seeded objects report binary/octet-stream even though the real
    // type is known — classification must fall back to the extension.
    expect(getPreviewKind("binary/octet-stream", "report.pdf")).toBe("pdf");
    expect(getPreviewKind("application/octet-stream", "sheet.xlsx")).toBe("spreadsheet");
    expect(getPreviewKind("binary/octet-stream", "photo.png")).toBe("image");
    expect(getPreviewKind("application/octet-stream", "notes.docx")).toBe("word");
  });

  it("is case-insensitive on mime type", () => {
    expect(getPreviewKind("IMAGE/PNG", "a.PNG")).toBe("image");
  });
});
