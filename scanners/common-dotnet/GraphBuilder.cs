using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.FileSystemGlobbing;

namespace Graph.Common;

/// <summary>Collects nodes/edges for one repo, stamping every edge with file, location, method, confidence, commit and repo.</summary>
public class GraphBuilder
{
    public readonly Fragment Fragment;
    private readonly Dictionary<string, Node> _nodes = new();
    private readonly HashSet<string> _edgeIds = new();
    private readonly RepoConfig _repo;
    private readonly SyntheticRules _synth;
    private readonly Dictionary<string, string[]> _lineCache = new();

    public string RepoRoot => _repo.AbsPath;
    public string RepoName => _repo.Name;

    public GraphBuilder(RepoConfig repo, SyntheticRules synth, string scannerName, string version)
    {
        _repo = repo; _synth = synth;
        Fragment = new Fragment
        {
            Repo = repo.Name,
            CommitId = Git.CommitForPath(repo.AbsPath),
            ScannedAt = DateTime.UtcNow.ToString("o"),
            Scanner = new ScannerInfo { Name = scannerName, Version = version }
        };
    }

    public string[] Lines(string relFile)
    {
        if (!_lineCache.TryGetValue(relFile, out var l))
            _lineCache[relFile] = l = File.ReadAllLines(Path.Combine(_repo.AbsPath, relFile));
        return l;
    }

    public string LineText(string relFile, int line)
    {
        var l = Lines(relFile);
        return line >= 1 && line <= l.Length ? l[line - 1].Trim() : "";
    }

    public bool IsSynthetic(string relFile, int line) =>
        _synth.FileIsSynthetic(relFile, Lines(relFile)) || (line > 0 && LineText(relFile, line).Contains(_synth.HeaderMarker));

    public string NodeId(string kindSlug, string qname) => $"{_repo.Name}:{kindSlug}:{qname}";

    public Node AddNode(string kind, string qname, string name, string file, int line, int endLine, Dictionary<string, object> attrs = null, string idKind = null)
    {
        var id = NodeId((idKind ?? kind).ToLowerInvariant(), qname);
        if (_nodes.TryGetValue(id, out var existing)) return existing;
        var n = new Node
        {
            Id = id, Kind = kind, Name = name, Repo = _repo.Name, File = file,
            Location = file == null ? null : new Location { Line = line, EndLine = endLine },
            Synthetic = file != null && IsSynthetic(file, 0), Attrs = attrs
        };
        _nodes[id] = n; Fragment.Nodes.Add(n);
        return n;
    }

    public Node Get(string id) => _nodes.TryGetValue(id, out var n) ? n : null;

    public Edge AddEdge(string type, string source, string target, string file, int line, int col, int endLine, int endCol,
                        string method, string confidence, string reason = null, Dictionary<string, object> attrs = null)
    {
        var id = $"{type}|{source}|{target}|{file}:{line}:{col}";
        if (!_edgeIds.Add(id)) return null;
        var e = new Edge
        {
            Id = id, Type = type, Source = source, Target = target, SourceFile = file,
            Location = new Location { Line = line, Column = col, EndLine = endLine, EndColumn = endCol },
            AnalysisMethod = method, Confidence = confidence, CommitId = Fragment.CommitId, Repo = _repo.Name,
            Synthetic = IsSynthetic(file, line), Reason = reason, Evidence = LineText(file, line), Attrs = attrs
        };
        Fragment.Edges.Add(e);
        return e;
    }

    public void Write(string path)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var opts = new JsonSerializerOptions { WriteIndented = true, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull };
        File.WriteAllText(path, JsonSerializer.Serialize(Fragment, opts));
    }
}

public static class Git
{
    static string Run(string dir, string gitArgs)
    {
        var psi = new ProcessStartInfo("git", $"-C \"{dir}\" {gitArgs}") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        using var p = Process.Start(psi)!;
        var o = p.StandardOutput.ReadToEnd().Trim();
        var err = p.StandardError.ReadToEnd().Trim();
        p.WaitForExit();
        if (p.ExitCode != 0) throw new Exception($"git {gitArgs} failed in {dir}: {err}");
        return o;
    }

    /// <summary>
    /// Commit ID of a logical repo = last commit that touched its folder: git log -1 --format=%H -- &lt;path&gt;.
    /// Refuses to scan when the working tree has uncommitted changes (including untracked, non-ignored files),
    /// because the recorded commit would then not describe the scanned files.
    /// </summary>
    public static string CommitForPath(string dir)
    {
        var dirty = Run(dir, "status --porcelain --untracked-files=normal");
        if (dirty.Length > 0)
            throw new Exception($"Refusing to scan: the git working tree has uncommitted changes (first lines):\n{string.Join('\n', dirty.Split('\n').Take(5))}\nCommit or stash them so commit_id matches the scanned files.");
        var h = Run(dir, "log -1 --format=%H -- .");
        if (h.Length < 7) throw new Exception($"No commit found for path {dir}; commit the files before scanning.");
        return h;
    }
}

public static class Files
{
    public static IEnumerable<string> Enumerate(RepoConfig repo)
    {
        var m = new Matcher();
        foreach (var i in repo.Include) m.AddInclude(i);
        foreach (var e in repo.Exclude) m.AddExclude(e);
        return m.GetResultsInFullPath(repo.AbsPath).Select(f => Path.GetRelativePath(repo.AbsPath, f).Replace('\\', '/')).OrderBy(x => x, StringComparer.Ordinal);
    }
}
