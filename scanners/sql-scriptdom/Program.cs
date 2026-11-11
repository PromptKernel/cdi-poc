using System.Text.RegularExpressions;
using Graph.Common;
using Microsoft.SqlServer.TransactSql.ScriptDom;

// Usage: SqlScanner --config <config dir> --repo <name> --out <file.json> [--repo-path <dir>] [--only <file-with-relative-paths>]
var a = Args.Parse(args);
var configDir = Path.GetFullPath(a["config"]);
var (repo, synth) = Cfg.Repo(configDir, a["repo"], a.GetValueOrDefault("repo-path"));
var naming = Cfg.Load<NamingFile>(Path.Combine(configDir, "naming.yml"));
var g = new GraphBuilder(repo, synth, "scriptdom", "1.0");
var defaultSchema = naming.Sql.DefaultSchema;

var files = Files.Enumerate(repo).ToList();
if (a.TryGetValue("only", out var onlyPath))
{
    var only = File.ReadAllLines(onlyPath).Select(x => x.Trim()).Where(x => x.Length > 0).ToHashSet();
    files = files.Where(only.Contains).ToList();
}
g.Fragment.FilesScanned = files.Count;

string Qn(SchemaObjectName n) => $"{n.SchemaIdentifier?.Value ?? defaultSchema}.{n.BaseIdentifier.Value}";
bool IsTestFile(string f) => naming.Tests.Sql.TestDirMarkers.Any(m => ("/" + f).Contains("/" + m));

// ---------- Pass 1: parse + collect definitions ----------
var parser = new TSql170Parser(true);
var parsed = new List<(string file, TSqlScript script, IList<TSqlParserToken> tokens)>();
var defs = new Dictionary<string, Node>(StringComparer.OrdinalIgnoreCase); // "schema.name" -> node
var parseErrors = 0;
foreach (var f in files)
{
    using var rdr = new StringReader(File.ReadAllText(Path.Combine(repo.AbsPath, f)));
    var tree = parser.Parse(rdr, out var errs) as TSqlScript;
    if (errs.Count > 0) { parseErrors += errs.Count; foreach (var e in errs) Console.Error.WriteLine($"parse error {f}:{e.Line}: {e.Message}"); }
    if (tree == null) continue;
    parsed.Add((f, tree, tree.ScriptTokenStream));
    foreach (var batch in tree.Batches)
        foreach (var st in batch.Statements)
        {
            var (kind, name) = st switch
            {
                CreateTableStatement t => ("SQL_TABLE", t.SchemaObjectName),
                CreateViewStatement v => ("SQL_VIEW", v.SchemaObjectName),
                CreateProcedureStatement p when !IsTestFile(f) => ("SQL_PROC", p.ProcedureReference.Name),
                _ => (null, null)
            };
            if (kind == null) continue;
            var q = Qn(name);
            var (sl, el) = Span(st, tree.ScriptTokenStream);
            defs[q] = g.AddNode(kind, q, q, f, sl, el, null, kind);
        }
}

static (int, int) Span(TSqlFragment fr, IList<TSqlParserToken> toks)
{
    var last = toks[fr.LastTokenIndex];
    var end = last.Line + (last.Text?.Count(c => c == '\n') ?? 0);
    return (fr.StartLine, end);
}

// ---------- Pass 2: relationships ----------
foreach (var (file, tree, toks) in parsed)
{
    var text = File.ReadAllText(Path.Combine(repo.AbsPath, file));
    foreach (var batch in tree.Batches)
        foreach (var st in batch.Statements)
        {
            string ownerId; string ownerQ;
            if (st is CreateProcedureStatement cp && IsTestFile(file))
            {
                var tq = Qn(cp.ProcedureReference.Name);
                var (sl, el) = Span(st, toks);
                var covers = Regex.Matches(text, Regex.Escape(naming.Tests.AnnotationTag) + @"\s+([^\r\n]+)").Select(m => m.Groups[1].Value.Trim()).ToList();
                var node = g.AddNode("TEST", $"{file}::{tq}", tq, file, sl, el,
                    new Dictionary<string, object> { ["test_layer"] = "SQL", ["covers_annotation"] = covers });
                ownerId = node.Id; ownerQ = tq;
                Walk(st, file, ownerId, toks, text);
            }
            else if (st is CreateProcedureStatement or CreateViewStatement)
            {
                ownerQ = st is CreateProcedureStatement p ? Qn(p.ProcedureReference.Name) : Qn(((CreateViewStatement)st).SchemaObjectName);
                ownerId = defs[ownerQ].Id;
                Walk(st, file, ownerId, toks, text);
            }
        }
}

void Walk(TSqlStatement st, string file, string ownerId, IList<TSqlParserToken> toks, string text)
{
    var v = new RefVisitor();
    st.Accept(v);
    foreach (var (nt, isWrite) in v.Tables)
    {
        var q = Qn(nt.SchemaObject);
        if (nt.SchemaObject.BaseIdentifier.Value.StartsWith("#") || v.CteNames.Contains(nt.SchemaObject.BaseIdentifier.Value)) continue;
        var (line, col) = (nt.StartLine, nt.StartColumn);
        var (eLine, eCol) = (toks[nt.LastTokenIndex].Line, toks[nt.LastTokenIndex].Column + toks[nt.LastTokenIndex].Text.Length);
        if (defs.TryGetValue(q, out var target))
        {
            var type = target.Kind == "SQL_VIEW" ? "READS_VIEW" : isWrite ? "WRITES_TABLE" : "READS_TABLE";
            g.AddEdge(type, ownerId, target.Id, file, line, col, eLine, eCol, "scriptdom:table-reference", "CONFIRMED_STATIC");
        }
        else
        {
            var rid = g.AddNode("SQL_REF", q, q, null, 0, 0, new Dictionary<string, object> { ["expected"] = "table_or_view" }).Id;
            g.AddEdge(isWrite ? "WRITES_TABLE" : "READS_TABLE", ownerId, rid, file, line, col, eLine, eCol, "scriptdom:table-reference", "UNRESOLVED",
                $"referenced object '{q}' not defined in scanned repo '{repo.Name}'");
        }
    }
    foreach (var ex in v.Executes)
    {
        var (line, col) = (ex.StartLine, ex.StartColumn);
        var (eLine, eCol) = (toks[ex.LastTokenIndex].Line, toks[ex.LastTokenIndex].Column + toks[ex.LastTokenIndex].Text.Length);
        string procName = (ex.ExecuteSpecification.ExecutableEntity as ExecutableProcedureReference)?.ProcedureReference?.ProcedureReference?.Name is { } n ? Qn(n) : null;
        var isDynamic = procName == null || procName.EndsWith(".sp_executesql", StringComparison.OrdinalIgnoreCase);
        if (isDynamic)
        {
            var uid = g.AddNode("UNRESOLVED", $"{file}:{line}", $"dynamic SQL at {file}:{line}", file, line, line,
                new Dictionary<string, object> { ["cause"] = "dynamic_sql" }).Id;
            g.AddEdge("EXECUTES_DYNAMIC_SQL", ownerId, uid, file, line, col, eLine, eCol, "scriptdom:exec-string", "UNRESOLVED",
                "dynamic SQL: statement text is built at runtime (string concatenation/variable); tables it touches cannot be resolved statically");
        }
        else if (defs.TryGetValue(procName, out var pt))
            g.AddEdge("CALLS_PROCEDURE", ownerId, pt.Id, file, line, col, eLine, eCol, "scriptdom:exec-procedure", "CONFIRMED_STATIC");
        else
        {
            var rid = g.AddNode("SQL_REF", procName, procName, null, 0, 0, new Dictionary<string, object> { ["expected"] = "procedure" }).Id;
            g.AddEdge("CALLS_PROCEDURE", ownerId, rid, file, line, col, eLine, eCol, "scriptdom:exec-procedure", "UNRESOLVED",
                $"referenced procedure '{procName}' not defined in scanned repo '{repo.Name}'");
        }
    }
}

g.Write(a["out"]);
Console.WriteLine($"[sql-scriptdom] {repo.Name}@{g.Fragment.CommitId[..8]} files={files.Count} nodes={g.Fragment.Nodes.Count} edges={g.Fragment.Edges.Count} parseErrors={parseErrors} -> {a["out"]}");

class RefVisitor : TSqlFragmentVisitor
{
    public List<(NamedTableReference, bool)> Tables = new();
    public List<ExecuteStatement> Executes = new();
    public HashSet<string> CteNames = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<TSqlFragment> _writes = new();

    public override void ExplicitVisit(InsertSpecification n) { if (n.Target is NamedTableReference t) _writes.Add(t); base.ExplicitVisit(n); }
    public override void ExplicitVisit(UpdateSpecification n) { if (n.Target is NamedTableReference t) _writes.Add(t); base.ExplicitVisit(n); }
    public override void ExplicitVisit(DeleteSpecification n) { if (n.Target is NamedTableReference t) _writes.Add(t); base.ExplicitVisit(n); }
    public override void ExplicitVisit(MergeSpecification n) { if (n.Target is NamedTableReference t) _writes.Add(t); base.ExplicitVisit(n); }
    public override void ExplicitVisit(CommonTableExpression n) { CteNames.Add(n.ExpressionName.Value); base.ExplicitVisit(n); }
    public override void ExplicitVisit(NamedTableReference n) { Tables.Add((n, _writes.Contains(n))); base.ExplicitVisit(n); }
    public override void ExplicitVisit(ExecuteStatement n) { Executes.Add(n); base.ExplicitVisit(n); }
}

static class Args
{
    public static Dictionary<string, string> Parse(string[] args)
    {
        var d = new Dictionary<string, string>();
        for (int i = 0; i < args.Length - 1; i += 2) d[args[i].TrimStart('-')] = args[i + 1];
        return d;
    }
}
