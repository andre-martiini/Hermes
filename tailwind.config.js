/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./index.tsx",
    "./*.tsx",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'surface': '#F9F8F6',         // Technical Paper
        'on-surface': '#212121',      // Deep Ink
        'primary-tactile': '#73A9E6', // Atmospheric Blue (Operational)
        'accent-tactile': '#FF9D4D',  // Alert Orange
        'highlighter': '#FDE68A',     // Highlighter Yellow
        'border-grid': '#E5E7EB',     // Fine Grid Lines
        'text-main': '#212121',
      },
      fontFamily: {
        serif: ['Newsreader', 'serif'],
        mono: ['JetBrains Mono', 'monospace'],
        lcd: ['DSEG7Classic', 'Space Mono', 'monospace'],
      },
      boxShadow: {
        'soft-touch': 'inset 2px 2px 4px rgba(0,0,0,0.05), inset -2px -2px 4px rgba(255,255,255,0.8)',
        'lcd-panel': 'inset 0 1px 3px rgba(0,0,0,0.2), 0 1px 0 rgba(255,255,255,0.5)',
      },
      borderRadius: {
        'soft-touch': '4px', // For interactive elements
        'lcd': '2px',         // For display panels
        'none': '0px',        // For structural elements
      },
    },
  },
  plugins: [],
};
