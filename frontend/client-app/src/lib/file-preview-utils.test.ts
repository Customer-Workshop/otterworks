import { describe, expect, it } from "vitest";
import {
  MAX_OFFICE_PREVIEW_BYTES,
  MAX_PREVIEW_COLS,
  MAX_PREVIEW_ROWS,
  capGrid,
  isPreviewTooLarge,
  previewKindFor,
} from "./file-preview-utils";

describe("previewKindFor", () => {
  it("AC-05/BDD-05: xlsx mime maps to spreadsheet preview", () => {
    expect(previewKindFor(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "report.xlsx",
    )).toBe("spreadsheet");
  });

  it("AC-05/BDD-05: legacy Excel mime maps to spreadsheet preview", () => {
    expect(previewKindFor("application/vnd.ms-excel", "report.xls")).toBe("spreadsheet");
  });

  it("AC-06/BDD-06: csv maps to spreadsheet before generic text", () => {
    expect(previewKindFor("text/csv", "rows.csv")).toBe("spreadsheet");
    expect(previewKindFor("text/plain", "rows.csv")).toBe("spreadsheet");
  });

  it("AC-07/BDD-07: docx maps to document preview", () => {
    expect(previewKindFor(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "brief.docx",
    )).toBe("document");
    expect(previewKindFor("application/octet-stream", "brief.docx")).toBe("document");
  });

  it("AC-02/BDD-02: image corpus types map to image preview", () => {
    expect(previewKindFor("image/png", "image.png")).toBe("image");
    expect(previewKindFor("image/jpeg", "image.jpeg")).toBe("image");
    expect(previewKindFor("image/svg+xml", "logo.svg")).toBe("image");
  });

  it("AC-03/BDD-03: PDF maps to pdf preview", () => {
    expect(previewKindFor("application/pdf", "report.pdf")).toBe("pdf");
  });

  it("AC-04/BDD-04: seeded text corpus maps to text preview", () => {
    expect(previewKindFor("text/markdown", "readme.md")).toBe("text");
    expect(previewKindFor("application/json", "data.json")).toBe("text");
    expect(previewKindFor("application/octet-stream", "script.sh")).toBe("generic");
    expect(previewKindFor("application/x-sh", "script.sh")).toBe("text");
  });

  it("AC-09/BDD-09: video maps to video preview", () => {
    expect(previewKindFor("video/mp4", "clip.mp4")).toBe("video");
  });

  it("AC-08/BDD-08: audio maps to audio preview", () => {
    expect(previewKindFor("audio/wav", "spot.wav")).toBe("audio");
  });

  it("AC-10/BDD-10 and AC-11/BDD-11: unsupported files use generic preview", () => {
    expect(previewKindFor(
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "deck.pptx",
    )).toBe("generic");
    expect(previewKindFor("application/zip", "archive.zip")).toBe("generic");
    expect(previewKindFor("application/octet-stream", "unknown.bin")).toBe("generic");
  });
});

describe("isPreviewTooLarge", () => {
  it("AC-16/BDD-16: office previews allow exactly 10 MB but reject one byte more", () => {
    expect(isPreviewTooLarge("spreadsheet", MAX_OFFICE_PREVIEW_BYTES)).toBe(false);
    expect(isPreviewTooLarge("document", MAX_OFFICE_PREVIEW_BYTES)).toBe(false);
    expect(isPreviewTooLarge("spreadsheet", MAX_OFFICE_PREVIEW_BYTES + 1)).toBe(true);
    expect(isPreviewTooLarge("document", MAX_OFFICE_PREVIEW_BYTES + 1)).toBe(true);
  });

  it("AC-19/BDD-04: text and streamed media are not rejected by office cap", () => {
    expect(isPreviewTooLarge("text", MAX_OFFICE_PREVIEW_BYTES + 1)).toBe(false);
    expect(isPreviewTooLarge("image", MAX_OFFICE_PREVIEW_BYTES + 1)).toBe(false);
  });
});

describe("capGrid", () => {
  it("AC-05/BDD-05: caps rows and columns and stringifies cells", () => {
    const rows = Array.from({ length: MAX_PREVIEW_ROWS + 1 }, (_, row) =>
      Array.from({ length: MAX_PREVIEW_COLS + 1 }, (_, col) =>
        row === 0 && col === 0 ? null : row * col,
      ),
    );

    const result = capGrid(rows);

    expect(result.rows).toHaveLength(MAX_PREVIEW_ROWS);
    expect(result.rows[0]).toHaveLength(MAX_PREVIEW_COLS);
    expect(result.rows[0][0]).toBe("");
    expect(result.rows[1][1]).toBe("1");
    expect(result.truncatedRows).toBe(true);
    expect(result.truncatedCols).toBe(true);
  });

  it("AC-06/BDD-06: reports no truncation for a small CSV grid", () => {
    expect(capGrid([["Name", 42], [undefined, true]])).toEqual({
      rows: [["Name", "42"], ["", "true"]],
      truncatedRows: false,
      truncatedCols: false,
    });
  });
});
