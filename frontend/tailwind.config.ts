import type { Config } from "tailwindcss";

/**
 * Colors map to the CSS variables defined in app/globals.css so nothing is
 * hard-coded — components are built against the tokens (the design system).
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
        "text-faint": "var(--text-faint)",
        "chat-surface": "var(--chat-surface)",
        "bubble-agent": "var(--bubble-agent)",
        "bubble-user": "var(--bubble-user)",
        primary: "var(--primary)",
        "primary-hover": "var(--primary-hover)",
        accent: "var(--accent)",
        resolved: "var(--resolved)",
        escalated: "var(--escalated)",
        pending: "var(--pending)",
        info: "var(--info)",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        sm: "var(--radius-sm)",
        lg: "var(--radius-lg)",
      },
      keyframes: {
        "pulse-iris": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "fade-slide": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "draw-spine": {
          from: { transform: "scaleY(0)" },
          to: { transform: "scaleY(1)" },
        },
      },
      animation: {
        "pulse-iris": "pulse-iris 1.4s ease-in-out infinite",
        "fade-slide": "fade-slide 0.2s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
