/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'mono': ['JetBrains Mono', 'Consolas', 'Monaco', 'Courier New', 'monospace'],
      },
      colors: {
        'terminal': {
          'bg': '#1a1a1a',
          'fg': '#ffffff',
          'cursor': '#00ff88',
          'accent': '#00ff88'
        }
      }
    },
  },
  plugins: [],
}