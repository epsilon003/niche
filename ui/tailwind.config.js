/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Layered-surface hierarchy (Apple dark mode: true black -> graphite -> lighter graphite),
        // not a single card color with a drop-shadow — depth comes from the layering itself.
        base: '#000000',
        surface: '#1c1c1e',
        surface2: '#2c2c2e',
        hairline: 'rgba(255,255,255,0.08)',
        hairline2: 'rgba(255,255,255,0.14)',
        // Text hierarchy matches Apple's label/secondaryLabel/tertiaryLabel dark-mode values.
        ink: '#f5f5f7',
        ink2: 'rgba(235,235,245,0.60)',
        ink3: 'rgba(235,235,245,0.30)',
        // One accent for action/focus; green/red reserved for market meaning; amber for caution.
        accent: '#0a84ff',
        positive: '#30d158',
        negative: '#ff453a',
        caution: '#ff9f0a',
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"', '"SF Pro Text"',
          'system-ui', '"Segoe UI"', 'Roboto', 'sans-serif',
        ],
      },
      borderRadius: {
        card: '18px',
        control: '10px',
      },
      backdropBlur: {
        material: '24px',
      },
    },
  },
  plugins: [],
}
