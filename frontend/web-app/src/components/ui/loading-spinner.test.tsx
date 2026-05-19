import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { LoadingSpinner, PageLoader } from "./loading-spinner";

describe("LoadingSpinner", () => {
  it("renders with role=status", () => {
    render(<LoadingSpinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-label Loading", () => {
    render(<LoadingSpinner />);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("applies size classes", () => {
    const { container: sm } = render(<LoadingSpinner size="sm" />);
    expect(sm.firstChild).toHaveClass("w-4");

    const { container: lg } = render(<LoadingSpinner size="lg" />);
    expect(lg.firstChild).toHaveClass("w-12");
  });

  it("applies custom className", () => {
    const { container } = render(<LoadingSpinner className="extra-class" />);
    expect(container.firstChild).toHaveClass("extra-class");
  });
});

describe("PageLoader", () => {
  it("renders a large spinner", () => {
    render(<PageLoader />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
