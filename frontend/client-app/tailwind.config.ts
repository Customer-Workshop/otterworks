import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        otter: {
          50: "#f0f7ff",
          100: "#e0efff",
          200: "#b9dfff",
          300: "#7cc5ff",
          400: "#36a9ff",
          500: "#0c8fff",
          600: "#0066cc",
          700: "#0055b3",
          800: "#004794",
          900: "#003d7a",
        },
      },
    },
  },
  plugins: [],
};

export default config;
