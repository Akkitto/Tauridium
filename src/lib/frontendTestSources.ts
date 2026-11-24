/** Static contracts follow real component imports and DOM/style ownership. */
import appSource from "../App.svelte?raw";
import { parse, type AST } from "svelte/compiler";

type Expression = AST.ExpressionTag["expression"];
export type TemplateScope = ReadonlyMap<string, string | Expression>;
const components = import.meta.glob<string>("../components/*.svelte", { query: "?raw", import: "default", eager: true });
const controllers = import.meta.glob<string>("./controllers/*.svelte.ts", { query: "?raw", import: "default", eager: true });
const sources = new Map<string, string>([["src/App.svelte", appSource]]);
for (const [key, value] of Object.entries(components)) sources.set(key.replace("../components/", "src/components/"), value);
for (const [key, value] of Object.entries(controllers)) sources.set(key.replace("./controllers/", "src/lib/controllers/"), value);

function relativePath(owner: string, relative: string): string {
  const parts = owner.split("/").slice(0, -1);
  for (const part of relative.split("/")) {
    if (part === "..") parts.pop();
    else if (part !== ".") parts.push(part);
  }
  const result = parts.join("/");
  return sources.has(result) ? result : result + ".ts";
}

const reachable = new Set<string>();
function follow(file: string): void {
  if (reachable.has(file)) return;
  const source = sources.get(file);
  if (!source) return;
  reachable.add(file);
  for (const match of source.matchAll(/(?:^|(?<=;))\s*import\s+(?!type\b)[^;]*?\bfrom\s*["']([^"']+)["']/gm)) {
    if (match[1].startsWith(".")) follow(relativePath(file, match[1]));
  }
}
follow("src/App.svelte");
export const frontendSource = [...reachable].map((file) => sources.get(file)).join("\n");
const owners = new WeakMap<object, string>();
const programs = new Map<string, ReturnType<typeof parse>>();
function record(value: unknown, file: string): void {
  if (!value || typeof value !== "object") return;
  owners.set(value, file);
  for (const child of Object.values(value)) {
    if (Array.isArray(child)) child.forEach((item) => record(item, file));
    else record(child, file);
  }
}
for (const file of reachable) {
  if (!file.endsWith(".svelte")) continue;
  const program = parse(sources.get(file) ?? "", { modern: true });
  programs.set(file, program);
  record(program, file);
}
const rootProgram = programs.get("src/App.svelte");
if (!rootProgram) throw new Error("Missing application template");
export const appAst = rootProgram;

export function sourceOf(value: object): string {
  const owner = owners.get(value);
  if (!owner) throw new Error("Unknown template owner");
  return sources.get(owner) ?? "";
}

export function resolveExpression(value: Expression, scope: TemplateScope, depth = 0): string | Expression {
  if (depth > 12 || value.type !== "Identifier") return value;
  const next = scope.get(value.name);
  if (next === undefined || typeof next !== "string" && next.type === "Identifier" && next.name === value.name) return value;
  return typeof next === "string" ? next : resolveExpression(next, scope, depth + 1);
}

export function staticText(value: Expression, scope: TemplateScope): string | undefined {
  const resolved = resolveExpression(value, scope);
  if (typeof resolved === "string") return resolved;
  if (resolved.type === "Literal") return typeof resolved.value === "string" || typeof resolved.value === "number" ? String(resolved.value) : undefined;
  if (resolved.type === "TemplateLiteral") {
    let result = resolved.quasis[0]?.value.cooked ?? "";
    for (let i = 0; i < resolved.expressions.length; i++) {
      const part = staticText(resolved.expressions[i], scope);
      if (part === undefined) return undefined;
      result += part + (resolved.quasis[i + 1]?.value.cooked ?? "");
    }
    return result;
  }
  return undefined;
}

function isComponent(value: unknown): value is AST.Component {
  return value !== null && typeof value === "object" && "type" in value && value.type === "Component";
}

export function componentTemplate(value: unknown, scope: TemplateScope): { fragment: AST.Fragment; scope: TemplateScope } | undefined {
  if (!isComponent(value) || !/^[A-Za-z_]\w*$/.test(value.name)) return;
  const owner = owners.get(value);
  if (!owner) return;
  const source = sources.get(owner) ?? "";
  const module = source.match(new RegExp('import\\s+' + value.name + '\\s+from\\s+["\\x27]([^"\\x27]+)["\\x27]'))?.[1];
  if (!module) return;
  const program = programs.get(relativePath(owner, module));
  if (!program) return;
  const childScope = new Map(scope);
  for (const attribute of value.attributes) {
    if (attribute.type === "BindDirective" && attribute.expression) childScope.set(attribute.name, resolveExpression(attribute.expression, scope));
    if (attribute.type !== "Attribute" || attribute.value === true) continue;
    const part = Array.isArray(attribute.value) ? attribute.value[0] : attribute.value;
    if (part?.type === "Text") childScope.set(attribute.name, part.data);
    if (part?.type === "ExpressionTag") childScope.set(attribute.name, resolveExpression(part.expression, scope));
  }
  return { fragment: program.fragment, scope: childScope };
}
