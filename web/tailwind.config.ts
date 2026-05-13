import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--color-ink)",
        sand: "var(--color-sand)",
        forest: "var(--color-forest)",
        mist: "var(--color-mist)",
        clay: "var(--color-clay)",
        sky: "var(--color-sky)",
        border: "var(--color-border)",
        card: "var(--color-card)",
      },
      fontFamily: {
        sans: ["Avenir Next", "Helvetica Neue", "sans-serif"],
        display: ["Iowan Old Style", "Georgia", "serif"],
      },
      boxShadow: {
        soft: "0 18px 45px rgba(16, 24, 20, 0.12)",
      },
      borderRadius: {
        shell: "24px",
      },
    },
  },
  plugins: [],
} satisfies Config;
