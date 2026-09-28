import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This storefront fetches from an external FastAPI service (not a
      // database colocated with the component), so the idiomatic
      // setLoading(true)/fetch/setLoading(false) effect pattern is used
      // throughout instead of the `use()` + Suspense rewrite this rule
      // wants — same tradeoff the Next.js docs' own "Community libraries"
      // (SWR/React Query) fetch example makes.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
