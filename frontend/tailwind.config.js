/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{html,ts}"],
  theme: {
    extend: {
      fontFamily: {
        montserrat: ['Montserrat', '-apple-system', 'Roboto', 'Helvetica', 'sans-serif'],
        inria: ['Inria Sans', '-apple-system', 'Roboto', 'Helvetica', 'sans-serif'],
      },
      colors: {
        'app-bg': '#ECF3FF',
        'app-black': '#000000',
        'app-white': '#FFFFFF',
        'app-text-secondary': '#4E5767',
        'app-border': 'rgba(134, 134, 148, 0.48)',
        'app-input-bg': '#F3F3F5',
        'app-tag-bg': '#C5C5CC',
        'app-accent': '#A6C6FF',
        'app-icon': '#868694',
        'app-slider-bg': '#ECECF0',
        'app-text-muted': '#616161',
        'app-text-icon': '#39393D',
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
