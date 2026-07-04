/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F7F2E7",
        "paper-line": "#DCD2B8",
        ink: "#1E2A44",
        "ink-soft": "#6B6354",
        seal: "#8C3A2E",
        registrar: "#2F6B4F",
        caution: "#A87C2A",
        steel: "#2E5677",
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        body: ["'Source Sans 3'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      keyframes: {
        stampDrop: {
          "0%": { transform: "translateY(-36px) rotate(-18deg) scale(1.35)", opacity: "0" },
          "55%": { transform: "translateY(2px) rotate(-4deg) scale(1.04)", opacity: "1" },
          "75%": { transform: "translateY(-1px) rotate(-7deg) scale(0.99)" },
          "100%": { transform: "translateY(0) rotate(-6deg) scale(1)" },
        },
        hover: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
      animation: {
        stamp: "stampDrop 0.6s cubic-bezier(0.34,1.56,0.64,1) forwards",
        hover: "hover 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
}
