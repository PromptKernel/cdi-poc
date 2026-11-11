using System.Text.RegularExpressions;
using Graph.Common;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

// Usage: CsScanner --config <config dir> --repo <name> --out <file.json> [--repo-path <dir>] [--only <file-with-relative-paths>]
// Note: the whole repo is always parsed so symbols resolve; --only restricts which files EMIT nodes/edges (PR overlay).
var a = new Dictionary<string, string>();
for (int i = 0; i < args.Length - 1; i += 2) a[args[i].TrimStart('-')] = args[i + 1];
var configDir = Path.GetFullPath(a["config"]);
var (repo, synth) = Cfg.Repo(configDir, a["repo"], a.GetValueOrDefault("repo-path"));
var routes = Cfg.Load<RoutesFile>(Path.Combine(configDir, "routes.yml")).Api;
var naming = Cfg.Load<NamingFile>(Path.Combine(configDir, "naming.yml"));
var g = new GraphBuilder(repo, synth, "roslyn", "1.0");

var files = Files.Enumerate(repo).ToList();
var emitFiles = files.ToHashSet();
if (a.TryGetValue("only", out var onlyPath))
    emitFiles = File.ReadAllLines(onlyPath).Select(x => x.Trim()).Where(x => x.Length > 0).ToHashSet();
g.Fragment.FilesScanned = files.Count(emitFiles.Contains);
g.EmitFile = emitFiles.Contains;
if (a.ContainsKey("only")) g.MarkOverlay(emitFiles);

var trees = files.Select(f => CSharpSyntaxTree.ParseText(File.ReadAllText(Path.Combine(repo.AbsPath, f)), path: f)).ToList();
var tpa = ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")!).Split(Path.PathSeparator);
var refs = tpa.Where(p => Path.GetFileName(p).StartsWith("System.") || Path.GetFileName(p) is "mscorlib.dll" or "netstandard.dll")
              .Select(p => MetadataReference.CreateFromFile(p)).ToList();
var comp = CSharpCompilation.Create("scan", trees, refs, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

var fmt = new SymbolDisplayFormat(
    typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypesAndNamespaces,
    memberOptions: SymbolDisplayMemberOptions.IncludeContainingType | SymbolDisplayMemberOptions.IncludeParameters,
    parameterOptions: SymbolDisplayParameterOptions.IncludeType,
    miscellaneousOptions: SymbolDisplayMiscellaneousOptions.UseSpecialTypes | SymbolDisplayMiscellaneousOptions.ExpandNullable);
string Key(IMethodSymbol m) => m.OriginalDefinition.ToDisplayString(fmt);
string Rel(SyntaxTree t) => t.FilePath;
(int l, int c, int el, int ec) Pos(SyntaxNode n)
{
    var s = n.GetLocation().GetLineSpan();
    return (s.StartLinePosition.Line + 1, s.StartLinePosition.Character + 1, s.EndLinePosition.Line + 1, s.EndLinePosition.Character + 1);
}
string AttrName(AttributeSyntax at) { var n = at.Name.ToString(); n = n.Split('.').Last(); return n.EndsWith("Attribute") ? n[..^9] : n; }
IEnumerable<AttributeSyntax> Attrs(MemberDeclarationSyntax m) => m.AttributeLists.SelectMany(l => l.Attributes);
string FirstStringArg(AttributeSyntax at) => at == null ? null :
    at.ArgumentList?.Arguments.Select(x => x.Expression).OfType<LiteralExpressionSyntax>().FirstOrDefault(l => l.IsKind(SyntaxKind.StringLiteralExpression))?.Token.ValueText;
var defaultSchema = naming.Sql.DefaultSchema;
var layerRules = naming.Layers.Select(l => (re: new Regex(l.Match), kind: l.Kind)).ToList();
string NormRoute(string t) => Regex.Replace(t.Trim('/'), @"\{[^}]*\}", "{}");

bool IsSqlCommand(BaseObjectCreationExpressionSyntax o, SemanticModel m)
{
    // Types are matched by NAME: System.Data.SqlClient / Microsoft.Data.SqlClient are not loaded as references.
    if (o is ObjectCreationExpressionSyntax oc) return oc.Type.ToString().Split('.').Last() == "SqlCommand";
    var ti = m.GetTypeInfo(o);
    if ((ti.ConvertedType?.Name ?? ti.Type?.Name) == "SqlCommand") return true; // target-typed new()
    return o.Parent is EqualsValueClauseSyntax { Parent: VariableDeclaratorSyntax { Parent: VariableDeclarationSyntax vd } } && vd.Type.ToString().Split('.').Last() == "SqlCommand";
}

// Command text: compile-time constant (literal, const field, constant concatenation) via the semantic model; else a local's initializer; else dynamic.
(string lit, string dynReason, string prefix) ResolveText(SemanticModel m, ExpressionSyntax e)
{
    if (e == null) return (null, "no command text found for this SqlCommand", null);
    ExpressionSyntax v = e;
    if (e is IdentifierNameSyntax && m.GetSymbolInfo(e).Symbol is ILocalSymbol ls &&
        ls.DeclaringSyntaxReferences.FirstOrDefault()?.GetSyntax() is VariableDeclaratorSyntax { Initializer.Value: { } init })
        v = init;
    var cv = m.GetConstantValue(v);
    if (cv.HasValue && cv.Value is string str) return (str, null, null);
    if (v is InterpolatedStringExpressionSyntax)
        return (null, "SQL text is an interpolated string with runtime values; tables it touches cannot be resolved statically", null);
    if (v is BinaryExpressionSyntax be && be.IsKind(SyntaxKind.AddExpression))
    {
        var left = be; while (left.Left is BinaryExpressionSyntax lb) left = lb;
        var lc = m.GetConstantValue(left.Left);
        return (null, "SQL text built by string concatenation with a runtime value; tables it touches cannot be resolved statically", lc.HasValue ? lc.Value as string : null);
    }
    return (null, "SQL command text is not a compile-time constant; cannot be resolved statically", null);
}

// ---------- DI registrations: AddTransient<IFoo, Foo>() ----------
var di = new Dictionary<string, (string file, int line, string impl)>();
foreach (var t in trees)
{
    var model = comp.GetSemanticModel(t);
    foreach (var gn in t.GetRoot().DescendantNodes().OfType<GenericNameSyntax>())
    {
        if (!(gn.Identifier.Text is "AddTransient" or "AddScoped" or "AddSingleton") || gn.TypeArgumentList.Arguments.Count != 2) continue;
        var ti = model.GetTypeInfo(gn.TypeArgumentList.Arguments[0]).Type; var tImpl = model.GetTypeInfo(gn.TypeArgumentList.Arguments[1]).Type;
        if (ti is { TypeKind: not TypeKind.Error } && tImpl is { TypeKind: not TypeKind.Error })
            di[ti.ToDisplayString(fmt)] = (Rel(t), gn.GetLocation().GetLineSpan().StartLinePosition.Line + 1, tImpl.ToDisplayString(fmt));
    }
}

// ---------- Pass 1: nodes ----------
var methodNodes = new Dictionary<string, Node>();
var testAttrs = naming.Tests.Csharp.TestAttributes.ToHashSet();
foreach (var t in trees) // nodes for the WHOLE repo (so edge targets in unchanged files resolve); only emitted files are written
{
    var model = comp.GetSemanticModel(t);
    foreach (var td in t.GetRoot().DescendantNodes().OfType<TypeDeclarationSyntax>())
    {
        var tsym = model.GetDeclaredSymbol(td);
        if (tsym == null) continue;
        var isIface = td is InterfaceDeclarationSyntax;
        var layer = layerRules.FirstOrDefault(l => l.re.IsMatch(td.Identifier.Text)).kind;
        var isController = td.Identifier.Text.EndsWith(routes.ControllerSuffix) ||
                           (td.BaseList?.Types.Any(b => routes.ControllerBaseClasses.Contains(b.Type.ToString())) ?? false);
        var classRoute = Attrs(td).Where(x => routes.RouteAttributes.Contains(AttrName(x))).Select(FirstStringArg).FirstOrDefault(x => x != null);
        foreach (var md in td.Members.OfType<MethodDeclarationSyntax>())
        {
            var msym = model.GetDeclaredSymbol(md);
            if (msym == null) continue;
            var key = Key(msym);
            var (l, c, el, ec) = Pos(md);
            var attrs = new Dictionary<string, object>();
            string kind;
            var isTest = Attrs(md).Any(x => testAttrs.Contains(AttrName(x)));
            if (!isTest && naming.Tests.Csharp.TestDirMarkers.Any(m => ("/" + Rel(t)).Contains("/" + m))) continue; // test helpers/fakes are not production nodes
            if (isTest)
            {
                kind = "TEST";
                var covers = md.GetLeadingTrivia().Where(x => x.IsKind(SyntaxKind.SingleLineCommentTrivia)).Select(x => x.ToString())
                    .Select(s => Regex.Match(s, Regex.Escape(naming.Tests.AnnotationTag) + @"\s+(\S.*)$")).Where(m => m.Success).Select(m => m.Groups[1].Value.Trim()).ToList();
                attrs["test_layer"] = "csharp";
                attrs["class"] = tsym.ToDisplayString(fmt);
                attrs["method_name"] = msym.Name;
                attrs["covers_annotation"] = covers;
            }
            else if (isIface) kind = "INTERFACE_METHOD";
            else if (isController && layer == "API_ENDPOINT")
            {
                var verbAttr = Attrs(md).FirstOrDefault(x => routes.VerbAttributes.ContainsKey(AttrName(x)));
                var routeAttr = Attrs(md).FirstOrDefault(x => routes.RouteAttributes.Contains(AttrName(x)));
                if (verbAttr == null && routeAttr == null) kind = "METHOD";
                else
                {
                    kind = "API_ENDPOINT";
                    var ctrlName = td.Identifier.Text.EndsWith(routes.ControllerSuffix) ? td.Identifier.Text[..^routes.ControllerSuffix.Length] : td.Identifier.Text;
                    var methodRoute = FirstStringArg(routeAttr) ?? (verbAttr != null ? FirstStringArg(verbAttr) : null);
                    var parts = new[] { classRoute, methodRoute }.Where(x => !string.IsNullOrEmpty(x))
                        .Select(x => x.Replace(routes.ControllerToken, ctrlName).Replace(routes.ActionToken, msym.Name)).ToList();
                    attrs["http_method"] = verbAttr != null ? routes.VerbAttributes[AttrName(verbAttr)] : "ANY";
                    if (parts.Count == 0) { attrs["route_template"] = null; attrs["route_unresolved_reason"] = "no attribute route; convention-based routing is not evaluated"; }
                    else
                    {
                        var tpl = string.Join("/", parts.Select(x => x.Trim('/')));
                        attrs["route_template"] = tpl; attrs["route_normalized"] = NormRoute(tpl);
                    }
                    attrs["class"] = tsym.ToDisplayString(fmt);
                }
            }
            else if (layer is "DATA_ACCESS_METHOD" or "SERVICE_METHOD") kind = layer;
            else kind = "METHOD";
            var n = g.AddNode(kind, key, key, Rel(t), l, el, attrs.Count == 0 ? null : attrs);
            methodNodes[key] = n;
        }
    }
}

// ---------- Pass 2: edges ----------
foreach (var t in trees.Where(t => emitFiles.Contains(Rel(t))))
{
    var model = comp.GetSemanticModel(t);
    var file = Rel(t);
    foreach (var md in t.GetRoot().DescendantNodes().OfType<MethodDeclarationSyntax>())
    {
        var msym = model.GetDeclaredSymbol(md);
        if (msym == null || !methodNodes.TryGetValue(Key(msym), out var owner)) continue;

        // interface -> implementation (INFERRED: runtime DI decides which implementation runs)
        foreach (var iface in msym.ContainingType.AllInterfaces)
            foreach (var im in iface.GetMembers().OfType<IMethodSymbol>())
                if (SymbolEqualityComparer.Default.Equals(msym.ContainingType.FindImplementationForInterfaceMember(im), msym))
                {
                    if (naming.Tests.Csharp.TestDirMarkers.Any(m => ("/" + file).Contains("/" + m))) continue;
                    var ik = Key(im);
                    if (!methodNodes.TryGetValue(ik, out var inode)) continue;
                    var (l, c, el, ec) = Pos(md.Identifier.Parent);
                    var ifaceName = iface.ToDisplayString(fmt);
                    var reg = di.TryGetValue(ifaceName, out var r) && r.impl == msym.ContainingType.ToDisplayString(fmt) ? r : default;
                    var reason = reg.file != null
                        ? $"interface call dispatched to implementing type; actual binding is a runtime DI decision (registration seen at {reg.file}:{reg.line})"
                        : "interface call dispatched to implementing type; no DI registration found in scanned sources";
                    g.AddEdge("DISPATCHES_TO", inode.Id, owner.Id, file, l, c, el, ec, "roslyn:interface-implementation+di-registration", "INFERRED", reason,
                        reg.file != null ? new() { ["di_registration"] = $"{reg.file}:{reg.line}" } : null);
                }

        if (owner.Kind == "TEST" || md.Body == null && md.ExpressionBody == null) continue;
        SyntaxNode body = (SyntaxNode)md.Body ?? md.ExpressionBody;

        // method -> method (semantic)
        foreach (var inv in body.DescendantNodes().OfType<InvocationExpressionSyntax>())
        {
            if (model.GetSymbolInfo(inv).Symbol is not IMethodSymbol callee) continue;
            if (!methodNodes.TryGetValue(Key(callee), out var target) || target.Id == owner.Id) continue;
            var (l, c, el, ec) = Pos(inv);
            g.AddEdge("CALLS", owner.Id, target.Id, file, l, c, el, ec, "roslyn:semantic-invocation", "CONFIRMED_STATIC");
        }

        // SqlCommand construction: new SqlCommand(...), target-typed new(...), object initializer, later CommandText/CommandType assignments
        foreach (var oc in body.DescendantNodes().OfType<BaseObjectCreationExpressionSyntax>().Where(o => IsSqlCommand(o, model)))
        {
            var (l, c, el, ec) = Pos(oc);
            string varName = oc.Parent is EqualsValueClauseSyntax { Parent: VariableDeclaratorSyntax d0 } ? d0.Identifier.Text
                           : oc.Parent is AssignmentExpressionSyntax { Left: IdentifierNameSyntax idl } ? idl.Identifier.Text : null;
            ExpressionSyntax textExpr = oc.ArgumentList?.Arguments.FirstOrDefault()?.Expression;
            string textSource = textExpr != null ? "constructor-argument" : null;
            bool isStoredProc = false;
            foreach (var asg in oc.Initializer?.Expressions.OfType<AssignmentExpressionSyntax>() ?? Enumerable.Empty<AssignmentExpressionSyntax>())
            {
                var lhs = asg.Left.ToString();
                if (lhs == "CommandText") { textExpr = asg.Right; textSource = "object-initializer"; }
                else if (lhs == "CommandType" && asg.Right.ToString().EndsWith("StoredProcedure")) isStoredProc = true;
            }
            if (varName != null)
                foreach (var asg in body.DescendantNodes().OfType<AssignmentExpressionSyntax>())
                {
                    var lhs = asg.Left.ToString();
                    if (lhs == varName + ".CommandText") { textExpr = asg.Right; textSource = "commandtext-assignment"; }
                    else if (lhs == varName + ".CommandType" && asg.Right.ToString().EndsWith("StoredProcedure")) isStoredProc = true;
                }
            var (lit, dynReason, prefix) = ResolveText(model, textExpr);

            if (lit != null && isStoredProc)
            {
                var q = lit.Contains('.') ? lit : $"{defaultSchema}.{lit}";
                var rid = g.AddNode("SQL_REF", q, q, null, 0, 0, new() { ["expected"] = "procedure" }).Id;
                g.AddEdge("CALLS_PROCEDURE", owner.Id, rid, file, l, c, el, ec, "roslyn:sqlcommand-storedprocedure", "CONFIRMED_STATIC", null,
                    new() { ["text_source"] = textSource });
            }
            else
            {
                var uid = g.AddNode("UNRESOLVED", $"{file}:{l}", $"inline/dynamic SQL at {file}:{l}", file, l, el,
                    new() { ["cause"] = lit != null ? "inline_sql_not_parsed" : "dynamic_sql", ["literal_prefix_hint"] = prefix }).Id;
                g.AddEdge("EXECUTES_DYNAMIC_SQL", owner.Id, uid, file, l, c, el, ec, "roslyn:sqlcommand-text",
                    "UNRESOLVED", dynReason ?? "inline SQL text (not a stored-procedure call); this PoC resolves stored-procedure calls only");
            }
        }
    }
}

g.Write(a["out"]);
Console.WriteLine($"[roslyn] {repo.Name}@{g.Fragment.CommitId[..8]} files={files.Count} nodes={g.Fragment.Nodes.Count} edges={g.Fragment.Edges.Count} -> {a["out"]}");
