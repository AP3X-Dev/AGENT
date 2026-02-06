import type { Config } from "tailwindcss"

const config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
    "*.{js,ts,jsx,tsx,mdx}",
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        /* VS Code Dark Theme Palette - Unified Dark */
        /* All main backgrounds match header for cohesive look */
        "primary-background": "#111111",     /* Main page background - matches header */
        surface: "#111111",                  /* Title bar, tab bar - unified */
        "surface-header": "#111111",         /* Header/toolbar */
        "surface-elevated": "#1e1e1e",       /* Elevated cards, hover states */
        "surface-secondary": "#111111",      /* Sidebar - matches header */
        "surface-input": "#181818",          /* Input fields - slightly lighter */

        /* Blue accent for message bubbles */
        "surface-accent": "#122e4e",         /* Message bubble background */
        "surface-accent-hover": "#163a5f",   /* Message bubble hover */

        /* Task rows */
        "surface-card": "#1e2222",           /* Task row dark cards */

        /* Text colors */
        "text-primary": "#f5f5f5",
        "text-secondary": "#a0a0a0",
        "text-muted": "#666666",
        "text-accent": "#4fc3f7",            /* Light blue accent text */

        /* Interactive elements */
        "interactive-primary": "#f5f5f5",
        "interactive-secondary": "#666666",
        "interactive-hover": "#2a2a2a",
        "interactive-active": "#333333",
        "interactive-border": "#2a2a2a",

        /* Status colors */
        "status-success": "#4ec9b0",         /* VS Code success green-teal */
        "status-warning": "#dcdcaa",         /* VS Code warning yellow */
        "status-error": "#f14c4c",           /* VS Code error red */
        "status-info": "#4fc3f7",            /* Light blue info */
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: [
          "var(--font-sora)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "var(--font-jetbrains-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
      fontSize: {
        xs: ['12px', { lineHeight: '1.25' }],
        sm: ['13px', { lineHeight: '1.25' }],
        base: ['15px', { lineHeight: '1.55' }],
        lg: ['18px', { lineHeight: '1.2' }],
        xl: ['20px', { lineHeight: '1.2' }],
        '2xl': ['28px', { lineHeight: '1.1' }],
        '3xl': ['32px', { lineHeight: '1.1' }],
      },
      lineHeight: {
        tight: '1.1',
        snug: '1.25',
        normal: '1.55',
      },
      letterSpacing: {
        tighter: '-0.02em',
        tight: '-0.01em',
        normal: '0em',
        wide: '0.01em',
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config

export default config
