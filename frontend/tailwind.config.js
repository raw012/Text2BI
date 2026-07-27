/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15,23,42,.04), 0 10px 30px rgba(15,23,42,.05)",
      },
    },
  },
  plugins: [],
};
