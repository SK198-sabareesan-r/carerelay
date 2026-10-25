/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Clinical teal - the primary brand color. Chosen over a generic
        // SaaS blue to read as clinical/health-tech software (Oscar,
        // Maven, most modern EHR/payer portals use this family) rather
        // than a developer dashboard.
        brand: {
          50: "#eefbf9",
          100: "#d4f3ee",
          200: "#aae6dd",
          300: "#75d2c4",
          400: "#3fb6a6",
          500: "#1f9a8c",
          600: "#167d72",
          700: "#146359",
          800: "#124f48",
          900: "#0f3f3a",
        },
        // Warm, paper-like neutrals for a light clinical canvas - these
        // replace the generic dark "slate" theme used throughout.
        ink: {
          25: "#fbfcfc",
          50: "#f7f9fb",
          100: "#eef1f4",
          200: "#dfe4e9",
          300: "#c7cdd4",
          400: "#9aa3ad",
          500: "#717b86",
          600: "#4f5861",
          700: "#394149",
          800: "#242a30",
          900: "#15191d",
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
        serif: ["Source Serif 4", "Georgia", "serif"],
      },
      boxShadow: {
        // Layered "elevation" shadows (ambient + contact light), the way
        // real depth is built in Figma/Material rather than one flat blur.
        xs: "0 1px 2px 0 rgba(15, 63, 58, 0.06)",
        card: "0 1px 1px rgba(15,63,58,0.04), 0 2px 4px -1px rgba(15,63,58,0.06), 0 8px 16px -4px rgba(15,63,58,0.06)",
        raised:
          "0 1px 1px rgba(15,63,58,0.05), 0 4px 8px -2px rgba(15,63,58,0.08), 0 16px 32px -8px rgba(15,63,58,0.10)",
        popover:
          "0 2px 4px rgba(15,23,24,0.06), 0 12px 24px -6px rgba(15,23,24,0.16), 0 24px 48px -12px rgba(15,23,24,0.12)",
        glow: "0 0 0 1px rgba(31,154,140,0.12), 0 8px 24px -4px rgba(31,154,140,0.25)",
        "inner-top": "inset 0 1px 0 0 rgba(255,255,255,0.6)",
      },
      backgroundImage: {
        // Soft mesh gradient "field" behind the whole app, so glass panels
        // have something real to refract instead of flat white.
        mesh: "radial-gradient(at 15% 0%, rgba(117,210,196,0.35) 0, transparent 55%), radial-gradient(at 85% 12%, rgba(63,182,166,0.22) 0, transparent 50%), radial-gradient(at 50% 100%, rgba(174,230,221,0.30) 0, transparent 60%), linear-gradient(180deg, #f3f8f7 0%, #eef5f3 100%)",
        "card-sheen": "linear-gradient(135deg, rgba(255,255,255,0.65) 0%, rgba(255,255,255,0.15) 60%)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgba(31,154,140,0.45)" },
          "70%": { boxShadow: "0 0 0 8px rgba(31,154,140,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(31,154,140,0)" },
        },
        "fade-in": {
          "0%": { opacity: 0, transform: "translateY(4px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px) rotate(var(--tilt, 0deg))" },
          "50%": { transform: "translateY(-6px) rotate(var(--tilt, 0deg))" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2s infinite",
        "fade-in": "fade-in 0.2s ease-out",
        float: "float 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
