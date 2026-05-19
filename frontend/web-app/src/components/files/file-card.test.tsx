import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

jest.mock("@/stores/auth-store", () => ({
  useAuthStore: () => ({ user: { id: "test-user" } }),
}));

jest.mock("@/lib/api", () => ({
  starredApi: {
    isStarred: jest.fn().mockReturnValue(false),
    toggle: jest.fn().mockReturnValue(true),
  },
}));

import { FileCard } from "./file-card";

const mockFile = {
  id: "file-1",
  name: "document.pdf",
  mimeType: "application/pdf",
  size: 1048576,
  parentId: null,
  ownerId: "user-1",
  ownerName: "Test User",
  isFolder: false,
  isTrashed: false,
  path: "/document.pdf",
  sharedWith: [],
  tags: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  versions: [],
};

describe("FileCard", () => {
  it("renders file name", () => {
    render(<FileCard file={mockFile as any} />);
    expect(screen.getByText("document.pdf")).toBeInTheDocument();
  });

  it("renders file size", () => {
    render(<FileCard file={mockFile as any} view="list" />);
    expect(screen.getByText(/1 MB/)).toBeInTheDocument();
  });
});
