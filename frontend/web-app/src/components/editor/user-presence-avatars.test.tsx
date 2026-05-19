import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { UserPresenceAvatars } from "./user-presence-avatars";

describe("UserPresenceAvatars", () => {
  const collaborators = [
    { userId: "1", name: "Alice Smith", color: "#ef4444", isOnline: true },
    { userId: "2", name: "Bob Jones", color: "#3b82f6", isOnline: false },
    { userId: "3", name: "Charlie Brown", color: "#22c55e", isOnline: true },
  ];

  it("renders nothing when collaborators is empty", () => {
    const { container } = render(<UserPresenceAvatars collaborators={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders avatars for collaborators", () => {
    render(<UserPresenceAvatars collaborators={collaborators} />);
    expect(screen.getByText("AS")).toBeInTheDocument();
    expect(screen.getByText("BJ")).toBeInTheDocument();
    expect(screen.getByText("CB")).toBeInTheDocument();
  });

  it("shows online count", () => {
    render(<UserPresenceAvatars collaborators={collaborators} />);
    expect(screen.getByText("2 online")).toBeInTheDocument();
  });

  it("limits visible avatars to maxVisible", () => {
    render(<UserPresenceAvatars collaborators={collaborators} maxVisible={2} />);
    expect(screen.getByText("AS")).toBeInTheDocument();
    expect(screen.getByText("BJ")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
  });
});
