import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        hockey: {
          bg: "#0a0e17",
          card: "#111827",
          border: "#1f2937",
          accent: "#ef4444",
          live: "#dc2626",
          khl: "#2563eb",
          vhl: "#16a34a",
          mhl: "#9333ea",
        },
      },
    },
  },
  plugins: [],
};
export default config;