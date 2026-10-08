/** Tokens de diseño: ver frontend/README.md. */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Public Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        tinta: { DEFAULT: '#1E2A36', suave: '#4A5866', tenue: '#7A8794' },
        papel: { DEFAULT: '#F2F4F0', linea: '#D8DED6', hondo: '#E6EAE3' },
        libro: { DEFAULT: '#2E6A4F', oscuro: '#21503B', claro: '#E3EFE8' },
        estado: {
          coincide: '#2E6A4F',
          discrepancia: '#A8661A',
          'discrepancia-claro': '#FBF0DF',
          nodeclarado: '#B42318',
          'nodeclarado-claro': '#FCE9E7',
          noreportado: '#5B6B7A',
          'noreportado-claro': '#ECEFF2',
        },
      },
    },
  },
  plugins: [],
}
