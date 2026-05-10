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
        'surface': '#f3f4f3',
        'surface-bright': '#fcf9f8',
        'surface-container': '#edeeed',
        'surface-container-low': '#f3f4f3',
        'on-surface': '#191c1c',
        'border-grid': '#dadada',
        'primary-tactile': '#835500', // Operational Orange/Brown
        'accent-tactile': '#0060ac',  // Cool Blue
        'lcd-bg': '#d9dad9',          // Muted greenish-grey for LCD
        'highlighter': '#E6FF00',    // For focus and highlights
        'text-main': '#191c1c',
      },
      fontFamily: {
        serif: ['JetBrains Mono', 'monospace'],
        mono: ['JetBrains Mono', 'monospace'],
        lcd: ['DSEG7Classic', 'Space Mono', 'monospace'],
      },
      boxShadow: {
        'soft-touch': 'inset 2px 2px 4px rgba(0,0,0,0.05), inset -2px -2px 4px rgba(255,255,255,0.8)',
        'lcd-panel': 'inset 0 1px 3px rgba(0,0,0,0.2), 0 1px 0 rgba(255,255,255,0.5)',
      },
      borderRadius: {
        'soft-touch': '24px', // For interactive elements
        'lcd': '4px',         // For display panels
        'none': '0px',        // For structural elements
      },
    },
  },
  plugins: [],
};
