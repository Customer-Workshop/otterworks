/**
 * Tests for the API client — axios instance, interceptors, token injection,
 * and snake_case → camelCase transform.
 */
import axios from "axios";

// Import the module to test
import { apiClient } from "./api-client";

// Mock localStorage
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

describe("apiClient", () => {
  it("has /api/v1 base URL", () => {
    expect(apiClient.defaults.baseURL).toBe("/api/v1");
  });

  it("sets Content-Type to application/json", () => {
    expect(apiClient.defaults.headers["Content-Type"]).toBe("application/json");
  });
});

describe("request interceptor", () => {
  it("adds Authorization header when token exists", async () => {
    localStorageMock.getItem.mockReturnValueOnce("test-token-123");
    const config = { headers: {} as Record<string, string> };

    // Simulate the interceptor by calling it
    const interceptors = (apiClient.interceptors.request as any).handlers;
    const requestInterceptor = interceptors[0].fulfilled;
    const result = await requestInterceptor(config);

    expect(result.headers.Authorization).toBe("Bearer test-token-123");
  });

  it("does not add Authorization header when no token", async () => {
    localStorageMock.getItem.mockReturnValueOnce(null);
    const config = { headers: {} as Record<string, string> };

    const interceptors = (apiClient.interceptors.request as any).handlers;
    const requestInterceptor = interceptors[0].fulfilled;
    const result = await requestInterceptor(config);

    expect(result.headers.Authorization).toBeUndefined();
  });
});

describe("response interceptor", () => {
  it("transforms snake_case keys to camelCase", async () => {
    const response = {
      data: { user_name: "test", file_size: 100, nested_obj: { inner_key: "val" } },
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    };

    const interceptors = (apiClient.interceptors.response as any).handlers;
    const responseInterceptor = interceptors[0].fulfilled;
    const result = await responseInterceptor(response);

    expect(result.data).toEqual({
      userName: "test",
      fileSize: 100,
      nestedObj: { innerKey: "val" },
    });
  });

  it("handles array data in response", async () => {
    const response = {
      data: [{ user_name: "a" }, { user_name: "b" }],
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    };

    const interceptors = (apiClient.interceptors.response as any).handlers;
    const responseInterceptor = interceptors[0].fulfilled;
    const result = await responseInterceptor(response);

    expect(result.data).toEqual([{ userName: "a" }, { userName: "b" }]);
  });

  it("handles null data gracefully", async () => {
    const response = {
      data: null,
      status: 204,
      statusText: "No Content",
      headers: {},
      config: {},
    };

    const interceptors = (apiClient.interceptors.response as any).handlers;
    const responseInterceptor = interceptors[0].fulfilled;
    const result = await responseInterceptor(response);

    expect(result.data).toBeNull();
  });
});
