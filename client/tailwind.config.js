/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      boxShadow: {
        soft: '0 14px 32px rgba(15, 23, 42, 0.10)',
      },
      colors: {
        brand: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
        },
        esg: {
          500: '#10b981',
          600: '#059669',
        },
      },
    },
  },
  corePlugins: {
    preflight: false,
  },
  plugins: [],
}
