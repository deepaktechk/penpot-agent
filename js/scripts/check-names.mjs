// Naming guard for the TypeScript sources: no cryptic one- or two-letter variable names.
//
// Every name a developer binds (const/let/var, function and arrow parameters, destructured names,
// catch parameters, function names) must say what it holds. Allowed conventions only: loop indexes
// i/j, coordinates x/y and deltas dx/dy, id, ok and the throwaway _. Same rule as tests/test_naming.py.
//
// How: esbuild strips the types of each file (identifiers are kept as written), esprima parses the
// JavaScript, and estraverse walks every binding. Exits 1 and lists the offending names.
import { transformSync } from "esbuild";
import esprima from "esprima";
import estraverse from "estraverse";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ALLOWED = new Set(["_", "i", "j", "x", "y", "dx", "dy", "id", "ok"]);
const MAX_SHORT = 2;
const ESBUILD_TEMP = /^_[a-z]\d*$/;        // temporaries esbuild adds when lowering `?.` / `??`
const SRC = new URL("../src/", import.meta.url).pathname;

function tsFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsFiles(path);
    return path.endsWith(".ts") && !path.endsWith(".d.ts") ? [path] : [];
  });
}

/** Identifiers bound by a pattern: `a`, `{ a, b: c }`, `[a, ...rest]`, `a = 1`. */
function patternNames(pattern) {
  if (!pattern) return [];
  switch (pattern.type) {
    case "Identifier": return [pattern.name];
    case "ObjectPattern": return pattern.properties.flatMap((prop) => patternNames(prop.type === "RestElement" ? prop : prop.value));
    case "ArrayPattern": return pattern.elements.flatMap(patternNames);
    case "RestElement": return patternNames(pattern.argument);
    case "AssignmentPattern": return patternNames(pattern.left);
    default: return [];
  }
}

function boundNames(ast) {
  const names = [];
  estraverse.traverse(ast, {
    enter(node) {
      // helpers esbuild injects when lowering syntax (`var __spreadValues = (a, b) => ...`) are not our code
      if (node.type === "VariableDeclarator" && node.id.type === "Identifier" && node.id.name.startsWith("__")) return this.skip();
      if (node.type === "VariableDeclarator") names.push(...patternNames(node.id));
      else if (node.type === "CatchClause") names.push(...patternNames(node.param));
      else if (/Function/.test(node.type)) {
        if (node.id) names.push(node.id.name);
        for (const param of node.params) names.push(...patternNames(param));
      }
    },
  });
  return names;
}

/** Line of the first declaration-like use of `name` in the original TypeScript (for the report). */
function lineOf(source, name) {
  const lines = source.split("\n");
  const declared = new RegExp(`(\\b(const|let|var|function|catch)\\s*\\(?\\s*|[({,\\[]\\s*|\\.\\.\\.)${name}\\b(?!\\s*:\\s*[{(])`);
  const index = lines.findIndex((line) => declared.test(line.replace(/\/\/.*$/, "")));
  return index + 1;
}

const problems = [];
for (const file of tsFiles(SRC)) {
  const source = readFileSync(file, "utf8");
  const { code } = transformSync(source, { loader: "ts", target: "es2017", format: "esm" });
  const ast = esprima.parseModule(code);
  for (const name of new Set(boundNames(ast))) {
    if (name.length <= MAX_SHORT && !ALLOWED.has(name) && !ESBUILD_TEMP.test(name)) {
      problems.push(`${relative(SRC, file)}:${lineOf(source, name)} ${name}`);
    }
  }
}
if (problems.length) {
  console.error(`rename these to descriptive names (${problems.length}):\n  ` + problems.sort().join("\n  "));
  process.exit(1);
}
console.log("check-names: ok");
