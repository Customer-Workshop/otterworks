import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Inbox } from "lucide-react";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title text", () => {
    render(<EmptyState icon={Inbox} title="No items" />);
    expect(screen.getByText("No items")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<EmptyState icon={Inbox} title="No items" description="Try uploading a file" />);
    expect(screen.getByText("Try uploading a file")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    const { container } = render(<EmptyState icon={Inbox} title="No items" />);
    expect(container.querySelectorAll("p").length).toBe(0);
  });

  it("renders action button when provided", () => {
    const onClick = jest.fn();
    render(<EmptyState icon={Inbox} title="No items" action={{ label: "Upload", onClick }} />);
    const button = screen.getByText("Upload");
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not render action button when not provided", () => {
    const { container } = render(<EmptyState icon={Inbox} title="Empty" />);
    expect(container.querySelectorAll("button").length).toBe(0);
  });
});
