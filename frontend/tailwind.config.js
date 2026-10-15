/** Design tokens: institutional navy + "cover" teal, cool paper background, status colours with meaning. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#14213D", 700: "#1F2F52", 500: "#3B4A6B", 300: "#8B95AB", 100: "#E3E7EF" },
        paper: "#F4F6F8",
        line: "#DDE2EA",
        cover: { DEFAULT: "#0E7C7B", dark: "#0A5F5E", light: "#E3F2F1" },
        ok: { DEFAULT: "#2F7D4F", light: "#E6F3EB" },
        warn: { DEFAULT: "#9A6412", light: "#FBF1DE" },
        bad: { DEFAULT: "#B42318", light: "#FBE9E7" },
        info: { DEFAULT: "#2457A6", light: "#E7EEF9" },
      },
      fontFamily: { sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"] },
      borderRadius: { DEFAULT: "6px" },
    },
  },
  plugins: [],
};
