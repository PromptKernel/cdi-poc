// ts-morph scanner. Usage:
//   node scan.mjs --config <config dir> --repo <name> --out <file.json> [--repo-path <dir>] [--only <file with relative paths>]
// The whole repo is always loaded so types resolve; --only restricts which files EMIT nodes/edges (PR overlay).
import { Project, SyntaxKind, Node } from "ts-morph";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import YAML from "yaml";
import fg from "fast-glob";

const args = {};
for (let i = 2; i < process.argv.length - 1; i += 2) args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
const configDir = path.resolve(args.config);
const load = (f) => YAML.parse(fs.readFileSync(path.join(configDir, f), "utf8"));
const reposCfg = load("repos.yml");
const routes = load("routes.yml");
const naming = load("naming.yml");
const repo = reposCfg.repos.find((r) => r.name === args.repo);
if (!repo) throw new Error(`repo '${args.repo}' not in repos.yml`);
const root = path.resolve(args["repo-path"] ?? (path.isAbsolute(repo.path) ? repo.path : path.join(configDir, "..", repo.path)));
const synth = reposCfg.synthetic ?? { path_segments: [], header_marker: "SYNTHETIC" };
const FE = routes.frontend;
const git = (a) => execFileSync("git", ["-C", root, ...a]).toString().trim();
// commit_id of a logical repo = last commit that touched its folder; refuse to scan a dirty working tree.
const dirty = git(["status", "--porcelain", "--untracked-files=normal"]);
if (dirty) {
  console.error(`Refusing to scan: the git working tree has uncommitted changes (first lines):\n${dirty.split("\n").slice(0, 5).join("\n")}\nCommit or stash them so commit_id matches the scanned files.`);
  process.exit(2);
}
const commit = git(["log", "-1", "--format=%H", "--", "."]);
if (commit.length < 7) { console.error(`No commit found for ${root}; commit the files before scanning.`); process.exit(2); }

// ---------- helpers mirroring Graph.Common (same id/edge shape) ----------
const fileLines = new Map();
const lines = (f) => fileLines.get(f) ?? (fileLines.set(f, fs.readFileSync(path.join(root, f), "utf8").split(/\r?\n/)), fileLines.get(f));
const lineText = (f, l) => (l >= 1 ? (lines(f)[l - 1] ?? "").trim() : "");
const fileSynthetic = (f) =>
  f.split("/").slice(0, -1).some((s) => synth.path_segments.includes(s)) || lines(f).slice(0, 5).some((l) => l.includes(synth.header_marker));
const lineSynthetic = (f, l) => fileSynthetic(f) || (l > 0 && lineText(f, l).includes(synth.header_marker));

const nodes = new Map();
const edgeIds = new Set();
const edges = [];
const nodeId = (kind, qn) => `${repo.name}:${kind.toLowerCase()}:${qn}`;
function addNode(kind, qn, name, file, line, endLine, attrs) {
  const id = nodeId(kind, qn);
  if (nodes.has(id)) return nodes.get(id);
  const n = { id, kind, name, repo: repo.name, synthetic: !!file && fileSynthetic(file) };
  if (file) { n.file = file; n.location = { line, end_line: endLine }; }
  if (attrs && Object.keys(attrs).length) n.attrs = attrs;
  nodes.set(id, n);
  return n;
}
function addEdge(type, source, target, file, node, method, confidence, reason, attrs) {
  const s = node.getSourceFile().getLineAndColumnAtPos(node.getStart());
  const e = node.getSourceFile().getLineAndColumnAtPos(node.getEnd());
  const id = `${type}|${source}|${target}|${file}:${s.line}:${s.column}`;
  if (edgeIds.has(id)) return;
  edgeIds.add(id);
  const edge = {
    id, type, source, target, source_file: file,
    location: { line: s.line, column: s.column, end_line: e.line, end_column: e.column },
    analysis_method: method, confidence, commit_id: commit, repo: repo.name,
    synthetic: lineSynthetic(file, s.line), evidence: lineText(file, s.line),
  };
  if (reason) edge.reason = reason;
  if (attrs) edge.attrs = attrs;
  edges.push(edge);
}

// ---------- load project ----------
const include = repo.include ?? ["**/*.ts"];
const allFiles = fg.sync(include, { cwd: root, ignore: repo.exclude ?? [], dot: false }).sort();
const emitSet = args.only ? new Set(fs.readFileSync(args.only, "utf8").split(/\r?\n/).map((s) => s.trim()).filter(Boolean)) : new Set(allFiles);
const tsconfig = path.join(root, "tsconfig.json");
const project = new Project({
  ...(fs.existsSync(tsconfig) ? { tsConfigFilePath: tsconfig, skipAddingFilesFromTsConfig: true } : {}),
  skipFileDependencyResolution: true,
});
for (const f of allFiles) project.addSourceFileAtPath(path.join(root, f));
const rel = (sf) => path.relative(root, sf.getFilePath()).split(path.sep).join("/");
const hasDecorator = (cls, names) => cls.getDecorators().some((d) => names.includes(d.getName()));
const isComponent = (c) => hasDecorator(c, FE.component_decorators);
const isService = (c) => hasDecorator(c, FE.service_decorators);

// ---------- URL folding ----------
class Unresolved extends Error {}
function foldUrl(expr, cls, method, depth = 0) {
  if (depth > 8) throw new Unresolved("expression too deep to fold");
  if (Node.isStringLiteral(expr) || Node.isNoSubstitutionTemplateLiteral(expr)) return expr.getLiteralText();
  if (Node.isTemplateExpression(expr)) {
    let s = expr.getHead().getLiteralText();
    for (const sp of expr.getTemplateSpans()) s += foldUrl(sp.getExpression(), cls, method, depth + 1, true) + sp.getLiteral().getLiteralText();
    return s;
  }
  if (Node.isParenthesizedExpression(expr)) return foldUrl(expr.getExpression(), cls, method, depth + 1);
  if (Node.isBinaryExpression(expr) && expr.getOperatorToken().getKind() === SyntaxKind.PlusToken)
    return foldUrl(expr.getLeft(), cls, method, depth + 1) + foldUrl(expr.getRight(), cls, method, depth + 1);
  if (Node.isCallExpression(expr)) {
    const txt = expr.getExpression().getText();
    if (FE.runtime_config_markers.some((m) => txt.endsWith(m) || txt.includes(m)))
      throw new Unresolved(`URL part comes from runtime configuration (${expr.getText()}); not statically resolvable`);
    throw new Unresolved(`URL part is the result of a call (${expr.getText()}); not statically resolvable`);
  }
  if (Node.isPropertyAccessExpression(expr) && expr.getExpression().getKind() === SyntaxKind.ThisKeyword) {
    // this.myAppUrl -> fold the assignment(s) to that property in the class
    const name = expr.getName();
    const assigns = cls.getDescendantsOfKind(SyntaxKind.BinaryExpression).filter(
      (b) => b.getOperatorToken().getKind() === SyntaxKind.EqualsToken && b.getLeft().getText() === `this.${name}`);
    if (assigns.length === 1) return foldUrl(assigns[0].getRight(), cls, method, depth + 1);
    const prop = cls.getProperty(name);
    if (prop?.getInitializer()) return foldUrl(prop.getInitializer(), cls, method, depth + 1);
    throw new Unresolved(`cannot find a single static assignment of this.${name}`);
  }
  if (Node.isIdentifier(expr)) {
    if (FE.base_url_identifiers.includes(expr.getText())) return ""; // deployment base URL, stripped
    // method parameter => path parameter
    if (method?.getParameters().some((p) => p.getName() === expr.getText())) return "{}";
    // constructor parameter that is a base url
    const ctor = cls.getConstructors()[0];
    if (ctor?.getParameters().some((p) => p.getName() === expr.getText() && FE.base_url_identifiers.includes(p.getName()))) return "";
    // local const
    const decl = expr.getSymbol()?.getDeclarations()?.[0];
    if (decl && Node.isVariableDeclaration(decl) && decl.getInitializer()) return foldUrl(decl.getInitializer(), cls, method, depth + 1);
    if (decl && Node.isParameterDeclaration(decl)) return "{}";
    throw new Unresolved(`identifier '${expr.getText()}' is not statically resolvable`);
  }
  if (expr.getKind() === SyntaxKind.PropertyAccessExpression || expr.getKind() === SyntaxKind.ElementAccessExpression)
    throw new Unresolved(`URL part '${expr.getText()}' is not statically resolvable`);
  throw new Unresolved(`unsupported URL expression '${expr.getText()}'`);
}
const normUrl = (u) => u.replace(/\?.*$/, "").replace(/^\/+/, "").replace(/\/{2,}/g, "/").replace(/\{[^}]*\}/g, routes.matching.param_token);

const isHttpClient = (recv) => {
  // this._http  -> declaration is a ctor parameter property or class property typed HttpClient
  const decl = Node.isPropertyAccessExpression(recv) ? recv.getNameNode().getSymbol()?.getDeclarations()?.[0]
            : Node.isIdentifier(recv) ? recv.getSymbol()?.getDeclarations()?.[0] : null;
  const tn = decl && (Node.isParameterDeclaration(decl) || Node.isPropertyDeclaration(decl)) ? decl.getTypeNode()?.getText() : null;
  return !!tn && FE.http_client_types.includes(tn);
};

// ---------- route table: { path, component } ----------
const routePaths = new Map(); // component class name -> [{path,file,line}]
for (const sf of project.getSourceFiles()) {
  for (const obj of sf.getDescendantsOfKind(SyntaxKind.ObjectLiteralExpression)) {
    const p = obj.getProperty("path"), c = obj.getProperty("component");
    if (!p || !c || !Node.isPropertyAssignment(p) || !Node.isPropertyAssignment(c)) continue;
    const pv = p.getInitializer(); if (!pv || !Node.isStringLiteral(pv)) continue;
    const list = routePaths.get(c.getInitializer().getText()) ?? [];
    list.push({ path: pv.getLiteralText(), file: rel(sf), line: obj.getStartLineNumber() });
    routePaths.set(c.getInitializer().getText(), list);
  }
}

// ---------- pass 1: nodes ----------
const classNode = new Map(); // ClassDeclaration -> node (component)
const methodNode = new Map(); // MethodDeclaration -> node (service method)
const isSpec = (f) => f.endsWith(naming.tests.typescript.spec_suffix);
for (const sf of project.getSourceFiles()) {
  const f = rel(sf);
  if (!emitSet.has(f) || isSpec(f)) continue;
  for (const cls of sf.getClasses()) {
    const cn = cls.getName();
    if (!cn) continue;
    if (isComponent(cls)) {
      const attrs = { screen_routes: (routePaths.get(cn) ?? []).map((r) => r.path) };
      const dec = cls.getDecorators().find((d) => d.getName() === "Component");
      const sel = dec?.getArguments()[0]?.getDescendantsOfKind(SyntaxKind.PropertyAssignment).find((p) => p.getName() === "selector");
      if (sel) attrs.selector = sel.getInitializer().getText().replace(/['"]/g, "");
      classNode.set(cls, addNode("UI_COMPONENT", cn, cn, f, cls.getStartLineNumber(), cls.getEndLineNumber(), attrs));
    } else if (isService(cls)) {
      for (const m of cls.getMethods())
        methodNode.set(m, addNode("UI_SERVICE_METHOD", `${cn}.${m.getName()}`, `${cn}.${m.getName()}`, f, m.getStartLineNumber(), m.getEndLineNumber()));
    }
  }
}

// ---------- pass 2: edges ----------
const modelNode = (decl) => {
  const f = rel(decl.getSourceFile());
  const nm = decl.getName();
  return addNode("UI_MODEL", nm, nm, f, decl.getStartLineNumber(), decl.getEndLineNumber());
};
function scanBody(cls, ownerNode, scope, method, file) {
  for (const call of scope.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    const callee = call.getExpression();
    if (!Node.isPropertyAccessExpression(callee)) continue;
    const verbName = callee.getName();

    // (1) HTTP client request (service methods only)
    if (FE.http_methods[verbName] && isHttpClient(callee.getExpression())) {
      const encl = call.getFirstAncestor((a) => Node.isMethodDeclaration(a) || Node.isConstructorDeclaration(a)) ?? method;
      const verb = FE.http_methods[verbName];
      const urlArg = call.getArguments()[0];
      try {
        const tpl = normUrl(foldUrl(urlArg, cls, encl));
        const rn = addNode("HTTP_REQUEST", `${verb} ${tpl}`, `${verb} ${tpl}`, file, call.getStartLineNumber(), call.getEndLineNumber(),
          { verb, url_template: tpl });
        addEdge("MAKES_REQUEST", ownerNode.id, rn.id, file, call, "tsmorph:http-url-fold", "CONFIRMED_STATIC");
      } catch (e) {
        if (!(e instanceof Unresolved)) throw e;
        const rn = addNode("UNRESOLVED", `${verb}@${file}:${call.getStartLineNumber()}`, `${verb} <unresolved URL> at ${file}:${call.getStartLineNumber()}`,
          file, call.getStartLineNumber(), call.getEndLineNumber(), { cause: "config_built_route", verb });
        addEdge("MAKES_REQUEST", ownerNode.id, rn.id, file, call, "tsmorph:http-url-fold", "UNRESOLVED", e.message);
      }
      continue;
    }

    // (2) call to another source-defined method (type resolved through declared property type)
    const decl = callee.getNameNode().getSymbol()?.getDeclarations()?.[0];
    if (decl && Node.isMethodDeclaration(decl) && methodNode.has(decl) && methodNode.get(decl) !== ownerNode)
      addEdge("CALLS", ownerNode.id, methodNode.get(decl).id, file, call, "tsmorph:type-resolved-call", "CONFIRMED_STATIC");
  }
  // (3) type references to source-defined models
  for (const tr of scope.getDescendantsOfKind(SyntaxKind.TypeReference)) {
    let sym = tr.getTypeName().getSymbol();
    if (sym?.isAlias()) sym = sym.getAliasedSymbol() ?? sym;
    const decl = sym?.getDeclarations()?.[0];
    if (!decl || !(Node.isInterfaceDeclaration(decl) || Node.isClassDeclaration(decl))) continue;
    if (Node.isClassDeclaration(decl) && (isComponent(decl) || isService(decl))) continue;
    if (decl.getSourceFile() === tr.getSourceFile() && decl === cls) continue;
    addEdge("USES_TYPE", ownerNode.id, modelNode(decl).id, file, tr, "tsmorph:type-reference", "CONFIRMED_STATIC");
  }
}
for (const sf of project.getSourceFiles()) {
  const f = rel(sf);
  if (!emitSet.has(f) || isSpec(f)) continue;
  for (const cls of sf.getClasses()) {
    if (classNode.has(cls)) scanBody(cls, classNode.get(cls), cls, null, f);
    else for (const m of cls.getMethods()) if (methodNode.has(m)) scanBody(cls, methodNode.get(m), m, m, f);
  }
}

// ---------- tests (*.spec.ts) ----------
const specSuffix = naming.tests.typescript.spec_suffix, srcSuffix = naming.tests.typescript.source_suffix;
const tag = naming.tests.annotation_tag;
const specFiles = project.getSourceFiles().filter((sf) => isSpec(rel(sf)) && emitSet.has(rel(sf)));
for (const sf of specFiles) {
  const f = rel(sf);
  const target = f.slice(0, -specSuffix.length) + srcSuffix;
  const fileCovers = [...sf.getFullText().matchAll(new RegExp(tag.replace("@", "@") + "\\s+(\\S.*)", "g"))].map((m) => m[1].trim());
  for (const call of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    if (call.getExpression().getText() !== "it") continue;
    const title = call.getArguments()[0]?.getText().replace(/^['"`]|['"`]$/g, "") ?? "";
    const desc = call.getFirstAncestor((a) => Node.isCallExpression(a) && a.getExpression().getText() === "describe");
    const suite = desc?.getArguments()[0]?.getText().replace(/^['"`]|['"`]$/g, "") ?? path.basename(f);
    addNode("TEST", `${f}::${suite} > ${title}`, `${suite} > ${title}`, f, call.getStartLineNumber(), call.getEndLineNumber(),
      { test_layer: "UNIT", covers_annotation: fileCovers, convention_target_file: fs.existsSync(path.join(root, target)) ? target : null });
  }
}

const fragment = {
  schema_version: "1.0", repo: repo.name, commit_id: commit, scanned_at: new Date().toISOString(),
  scanner: { name: "ts-morph", version: "1.0" }, files_scanned: [...emitSet].filter((x) => allFiles.includes(x)).length,
  nodes: [...nodes.values()], edges,
};
fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
fs.writeFileSync(args.out, JSON.stringify(fragment, null, 2));
console.log(`[ts-morph] ${repo.name}@${commit.slice(0, 8)} files=${allFiles.length} nodes=${fragment.nodes.length} edges=${edges.length} -> ${args.out}`);
