/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B0B0C",
        surface: "#151517",
        edge: "#26262A",
        paper: "#EDEAE4",
        muted: "#8A8A90",
        brass: "#C8A15A",
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Microsoft YaHei"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
