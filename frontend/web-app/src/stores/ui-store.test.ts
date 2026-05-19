import { useUIStore } from "./ui-store";

describe("useUIStore", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarOpen: true,
      viewMode: "grid",
      sortConfig: { field: "updatedAt", direction: "desc" },
    });
  });

  it("starts with sidebar open", () => {
    expect(useUIStore.getState().sidebarOpen).toBe(true);
  });

  it("toggleSidebar flips sidebarOpen", () => {
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(true);
  });

  it("setSidebarOpen sets exact value", () => {
    useUIStore.getState().setSidebarOpen(false);
    expect(useUIStore.getState().sidebarOpen).toBe(false);
  });

  it("defaults to grid viewMode", () => {
    expect(useUIStore.getState().viewMode).toBe("grid");
  });

  it("setViewMode changes the view mode", () => {
    useUIStore.getState().setViewMode("list");
    expect(useUIStore.getState().viewMode).toBe("list");
  });

  it("setSortConfig updates sort configuration", () => {
    useUIStore.getState().setSortConfig({ field: "name", direction: "asc" });
    expect(useUIStore.getState().sortConfig).toEqual({ field: "name", direction: "asc" });
  });
});
