/**
 * Tests for API utility functions — authApi, filesApi helpers.
 */
jest.mock("./api-client", () => {
  const mockAxiosInstance = {
    post: jest.fn(),
    get: jest.fn(),
    patch: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: { baseURL: "/api/v1", headers: { "Content-Type": "application/json" } },
  };
  return { apiClient: mockAxiosInstance };
});

import { apiClient } from "./api-client";
import { authApi } from "./api";

const mockClient = apiClient as jest.Mocked<typeof apiClient>;

describe("authApi", () => {
  afterEach(() => jest.clearAllMocks());

  describe("login", () => {
    it("posts credentials and returns tokens", async () => {
      const tokens = { accessToken: "abc", refreshToken: "xyz" };
      (mockClient.post as jest.Mock).mockResolvedValueOnce({ data: tokens });

      const result = await authApi.login({ email: "user@test.com", password: "pass" });

      expect(mockClient.post).toHaveBeenCalledWith("/auth/login", {
        email: "user@test.com",
        password: "pass",
      });
      expect(result).toEqual(tokens);
    });
  });

  describe("register", () => {
    it("posts registration data and returns tokens", async () => {
      const tokens = { accessToken: "abc", refreshToken: "xyz" };
      (mockClient.post as jest.Mock).mockResolvedValueOnce({ data: tokens });

      const result = await authApi.register({
        displayName: "Test User",
        email: "user@test.com",
        password: "pass",
      });

      expect(mockClient.post).toHaveBeenCalledWith("/auth/register", {
        displayName: "Test User",
        email: "user@test.com",
        password: "pass",
      });
      expect(result).toEqual(tokens);
    });
  });

  describe("getProfile", () => {
    it("fetches the user profile", async () => {
      const user = { id: "1", email: "user@test.com", displayName: "Test" };
      (mockClient.get as jest.Mock).mockResolvedValueOnce({ data: user });

      const result = await authApi.getProfile();

      expect(mockClient.get).toHaveBeenCalledWith("/auth/profile");
      expect(result).toEqual(user);
    });
  });

  describe("updateProfile", () => {
    it("patches the profile and returns updated user", async () => {
      const updated = { id: "1", displayName: "New Name" };
      (mockClient.patch as jest.Mock).mockResolvedValueOnce({ data: updated });

      const result = await authApi.updateProfile({ displayName: "New Name" });

      expect(mockClient.patch).toHaveBeenCalledWith("/auth/profile", { displayName: "New Name" });
      expect(result).toEqual(updated);
    });
  });

  describe("logout", () => {
    it("posts to logout endpoint", async () => {
      (mockClient.post as jest.Mock).mockResolvedValueOnce({});

      await authApi.logout();

      expect(mockClient.post).toHaveBeenCalledWith("/auth/logout");
    });
  });

  describe("lookupUser", () => {
    it("looks up a user by email", async () => {
      const user = { id: "1", email: "test@test.com", displayName: "Test" };
      (mockClient.get as jest.Mock).mockResolvedValueOnce({ data: user });

      const result = await authApi.lookupUser("test@test.com");

      expect(mockClient.get).toHaveBeenCalledWith("/auth/users/lookup", {
        params: { email: "test@test.com" },
      });
      expect(result).toEqual(user);
    });
  });

  describe("lookupUserById", () => {
    it("looks up a user by ID", async () => {
      const user = { id: "abc", email: "test@test.com", displayName: "Test" };
      (mockClient.get as jest.Mock).mockResolvedValueOnce({ data: user });

      const result = await authApi.lookupUserById("abc");

      expect(mockClient.get).toHaveBeenCalledWith("/auth/users/by-id/abc");
      expect(result).toEqual(user);
    });
  });
});
