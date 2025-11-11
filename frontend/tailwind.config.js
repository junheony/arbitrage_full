/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('daisyui'),
  ],
  daisyui: {
    themes: [
      {
        arbitrage: {
          "primary": "#00d0ff",
          "secondary": "#9873ff",
          "accent": "#ffc05b",
          "neutral": "#1c2b44",
          "base-100": "#0b121f",
          "base-200": "#141f35",
          "base-300": "#1c2b44",
          "info": "#00d0ff",
          "success": "#10b981",
          "warning": "#ffc05b",
          "error": "#ef4444",
        },
      },
    ],
  },
}
