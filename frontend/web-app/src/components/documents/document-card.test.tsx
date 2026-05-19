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

import { DocumentCard } from "./document-card";

const mockDocument = {
  id: "doc-1",
  title: "Test Document",
  content: "Some content here",
  ownerId: "user-1",
  ownerName: "Test User",
  wordCount: 3,
  collaborators: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

describe("DocumentCard", () => {
  it("renders document title", () => {
    render(<DocumentCard document={mockDocument as any} />);
    expect(screen.getByText("Test Document")).toBeInTheDocument();
  });

  it("renders in list view", () => {
    render(<DocumentCard document={mockDocument as any} view="list" />);
    expect(screen.getByText("Test Document")).toBeInTheDocument();
  });
});
