import type { Config } from "tailwindcss";

/**
 * Palet diambil dari frontend/design/Analyst.dc.html (sumber visual).
 * Aksen brand = copper #c78d4e (via CSS var --accent → gampang diflip ke hijau).
 * Warna semantik verify (pass/fail) terpisah dari brand.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0c0c0c",
        "bg-soft": "#0a0a0a",
        panel: "#141414",
        line: "#1f1f1f",
        line2: "#2a2a2a",
        ink: "#e8e8e8",
        muted: "#9a9a9a",
        faint: "#6b6b6b",
        accent: "var(--accent)",
        pass: "#5a9e6f",
        fail: "#b83a3a",
        warn: "#c79a4e",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      keyframes: {
        grow: { "0%": { width: "0" }, "100%": { width: "100%" } },
        fadein: { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: {
        grow: "grow 1.1s linear infinite",
        fadein: "fadein 0.25s ease",
      },
    },
  },
  plugins: [],
};

export default config;
