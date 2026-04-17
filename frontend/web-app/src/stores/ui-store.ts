import { create } from "zustand";
import type { ViewMode, SortConfig } from "@/types";

interface UIState {
  sidebarOpen: boolean;
  viewMode: ViewMode;
  sortConfig: SortConfig;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setViewMode: (mode: ViewMode) => void;
  setSortConfig: (config: SortConfig) => void;
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
