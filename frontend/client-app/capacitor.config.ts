import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.otterworks.app",
  appName: "OtterWorks",
  webDir: "dist",
  android: {
    path: "mobile/android",
    // Allow the https-scheme webview to call the plain-http API gateway on the
    // emulator host alias (10.0.2.2) during development, mirroring the old
    // native app's cleartext allowance. Point VITE_API_BASE_URL at an https
    // gateway for production builds.
    allowMixedContent: true,
  },
  ios: {
    path: "mobile/ios",
  },
};

export default config;
