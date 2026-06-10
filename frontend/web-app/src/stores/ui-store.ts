import { create } from "zustand";
import type { ViewMode, SortConfig } from "@/types";

interface UIState {
  readonly sidebarOpen: boolean;
  readonly viewMode: ViewMode;
  readonly sortConfig: SortConfig;
  readonly toggleSidebar: () => void;
  readonly setSidebarOpen: (open: boolean) => void;
  readonly setViewMode: (mode: ViewMode) => void;
  readonly setSortConfig: (config: SortConfig) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  viewMode: "grid",
  sortConfig: { field: "updatedAt", direction: "desc" },
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setViewMode: (viewMode) => set({ viewMode }),
  setSortConfig: (sortConfig) => set({ sortConfig }),
}));
