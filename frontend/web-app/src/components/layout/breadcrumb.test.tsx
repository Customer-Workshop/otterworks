import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Breadcrumb } from "./breadcrumb";

describe("Breadcrumb", () => {
  it("renders a home link", () => {
    render(<Breadcrumb items={[]} />);
    expect(screen.getByLabelText("Home")).toBeInTheDocument();
  });

  it("renders breadcrumb items with links", () => {
    render(
      <Breadcrumb
        items={[
          { label: "Files", href: "/files" },
          { label: "Documents" },
        ]}
      />
    );
    const link = screen.getByText("Files");
    expect(link.closest("a")).toHaveAttribute("href", "/files");
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("renders last item without link", () => {
    render(
      <Breadcrumb items={[{ label: "Current" }]} />
    );
    const el = screen.getByText("Current");
    expect(el.tagName).toBe("SPAN");
  });

  it("has proper nav aria label", () => {
    render(<Breadcrumb items={[]} />);
    expect(screen.getByLabelText("Breadcrumb")).toBeInTheDocument();
  });
});
