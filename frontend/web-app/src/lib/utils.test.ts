import { cn, formatFileSize, formatRelativeTime, getFileIcon, getInitials, generateColor, truncate } from "./utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("handles conditional classes", () => {
    expect(cn("a", false && "b", "c")).toBe("a c");
  });
});

describe("formatFileSize", () => {
  it("formats 0 bytes", () => {
    expect(formatFileSize(0)).toBe("0 B");
  });

  it("formats bytes", () => {
    expect(formatFileSize(500)).toBe("500 B");
  });

  it("formats kilobytes", () => {
    expect(formatFileSize(1024)).toBe("1 KB");
  });

  it("formats megabytes", () => {
    expect(formatFileSize(1048576)).toBe("1 MB");
  });

  it("formats gigabytes", () => {
    expect(formatFileSize(1073741824)).toBe("1 GB");
  });
});

describe("formatRelativeTime", () => {
  it('returns "just now" for recent times', () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe("just now");
  });

  it("returns minutes ago", () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe("5m ago");
  });

  it("returns hours ago", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(twoHoursAgo)).toBe("2h ago");
  });

  it("returns days ago", () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(threeDaysAgo)).toBe("3d ago");
  });
});

describe("getFileIcon", () => {
  it("returns 'image' for image types", () => {
    expect(getFileIcon("image/png")).toBe("image");
  });

  it("returns 'video' for video types", () => {
    expect(getFileIcon("video/mp4")).toBe("video");
  });

  it("returns 'music' for audio types", () => {
    expect(getFileIcon("audio/mpeg")).toBe("music");
  });

  it("returns 'file-text' for PDF", () => {
    expect(getFileIcon("application/pdf")).toBe("file-text");
  });

  it("returns 'table' for spreadsheets", () => {
    expect(getFileIcon("application/vnd.ms-excel")).toBe("table");
  });

  it("returns 'file' for unknown types", () => {
    expect(getFileIcon("application/octet-stream")).toBe("file");
  });
});

describe("getInitials", () => {
  it("returns initials for a full name", () => {
    expect(getInitials("Jane Doe")).toBe("JD");
  });

  it("returns single initial for single name", () => {
    expect(getInitials("Jane")).toBe("J");
  });

  it("truncates to 2 characters", () => {
    expect(getInitials("John Michael Doe")).toBe("JM");
  });
});

describe("generateColor", () => {
  it("returns a hex color string", () => {
    expect(generateColor("user-1")).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("returns the same color for the same seed", () => {
    expect(generateColor("test")).toBe(generateColor("test"));
  });
});

describe("truncate", () => {
  it("does not truncate short strings", () => {
    expect(truncate("hi", 10)).toBe("hi");
  });

  it("truncates long strings with ellipsis", () => {
    expect(truncate("Hello, World!", 8)).toBe("Hello...");
  });

  it("handles exact length", () => {
    expect(truncate("exact", 5)).toBe("exact");
  });
});
