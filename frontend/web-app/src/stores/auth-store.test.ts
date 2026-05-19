/**
 * Tests for the auth Zustand store.
 */
jest.mock("@/lib/api", () => ({
  authApi: { logout: jest.fn().mockResolvedValue(undefined) },
}));

import { useAuthStore } from "./auth-store";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] ?? null),
    setItem: jest.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: jest.fn((key: string) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(global, "localStorage", { value: localStorageMock });

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: true,
    });
    localStorageMock.clear();
  });

  it("starts with default state", () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(true);
  });

  it("setUser updates user and isAuthenticated", () => {
    const user = { id: "1", email: "test@test.com", displayName: "Test" } as any;
    useAuthStore.getState().setUser(user);
    const state = useAuthStore.getState();
    expect(state.user).toEqual(user);
    expect(state.isAuthenticated).toBe(true);
    expect(state.isLoading).toBe(false);
  });

  it("setUser with null clears authentication", () => {
    useAuthStore.getState().setUser({ id: "1" } as any);
    useAuthStore.getState().setUser(null);
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("setLoading updates loading state", () => {
    useAuthStore.getState().setLoading(false);
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it("logout clears tokens and state", () => {
    useAuthStore.getState().setUser({ id: "1" } as any);

    // jsdom throws on navigation; catch and ignore
    try {
      useAuthStore.getState().logout();
    } catch {
      // expected: "Not implemented: navigation"
    }

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("otter_access_token");
    expect(localStorageMock.removeItem).toHaveBeenCalledWith("otter_refresh_token");
  });
});
