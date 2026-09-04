/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        panel: '#12151c',
        base: '#0a0b0f',
        edge: '#232733',
      },
    },
  },
  plugins: [],
}
