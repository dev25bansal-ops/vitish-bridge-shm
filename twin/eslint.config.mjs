import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

// Minimal lint for the twin (ROADMAP line 89).  typescript-eslint `recommended`
// catches real scope/type hazards (no-explicit-any, no-unused-vars, prefer-const,
// ...); the react-hooks plugin is limited to the two classic, stable rules —
// v7's wider `recommended` (static-components, purity, immutability,
// set-state-in-effect, ...) targets React Compiler-era code and would drown the
// existing components in churn.
export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
)
