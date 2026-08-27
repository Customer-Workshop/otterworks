import { fixupConfigRules } from "@eslint/compat";
import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({
  baseDirectory: __dirname,
  resolvePluginsRelativeTo: path.join(
    __dirname,
    "node_modules/eslint-config-next",
  ),
});

export default [
  ...fixupConfigRules(compat.config({
    extends: [
      "plugin:react/recommended",
      "plugin:react-hooks/recommended",
      "plugin:@next/next/recommended",
      "plugin:@next/next/core-web-vitals",
    ],
    plugins: ["import", "react", "jsx-a11y"],
    parser: path.join(
      __dirname,
      "node_modules/eslint-config-next/parser.js",
    ),
    parserOptions: {
      requireConfigFile: false,
      sourceType: "module",
      allowImportExportEverywhere: true,
      babelOptions: {
        presets: ["next/babel"],
        caller: {
          supportsTopLevelAwait: true,
        },
      },
    },
    overrides: [
      {
        files: ["**/*.ts?(x)"],
        parser: "@typescript-eslint/parser",
        parserOptions: {
          sourceType: "module",
        },
      },
    ],
    settings: {
      react: {
        version: "detect",
      },
      "import/parsers": {
        "@typescript-eslint/parser": [
          ".ts",
          ".mts",
          ".cts",
          ".tsx",
          ".d.ts",
        ],
      },
      "import/resolver": {
        "eslint-import-resolver-node": {
          extensions: [".js", ".jsx", ".ts", ".tsx"],
        },
        "eslint-import-resolver-typescript": {
          alwaysTryTypes: true,
        },
      },
    },
    env: {
      browser: true,
      node: true,
    },
    rules: {
      "import/no-anonymous-default-export": "warn",
      "react/no-unknown-property": "off",
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "jsx-a11y/alt-text": [
        "warn",
        {
          elements: ["img"],
          img: ["Image"],
        },
      ],
      "jsx-a11y/aria-props": "warn",
      "jsx-a11y/aria-proptypes": "warn",
      "jsx-a11y/aria-unsupported-elements": "warn",
      "jsx-a11y/role-has-required-aria-props": "warn",
      "jsx-a11y/role-supports-aria-props": "warn",
      "react/jsx-no-target-blank": "off",
    },
  })),
  {
    ignores: [
      ".next/**",
      "out/**",
      "node_modules/**",
      "*.config.mjs",
      "*.config.ts",
    ],
  },
];
