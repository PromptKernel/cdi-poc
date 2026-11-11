using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Graph.Common;

public class RepoConfig
{
    public string Name { get; set; }
    public string Path { get; set; }
    public string Kind { get; set; }
    public string MainBranch { get; set; }
    public List<string> Include { get; set; } = new();
    public List<string> Exclude { get; set; } = new();
    [YamlIgnore] public string AbsPath { get; set; }
}

public class SyntheticRules
{
    public List<string> PathSegments { get; set; } = new();
    public string HeaderMarker { get; set; } = "SYNTHETIC";

    public bool FileIsSynthetic(string relFile, string[] lines)
    {
        var segs = relFile.Split('/');
        if (segs.Take(segs.Length - 1).Any(s => PathSegments.Contains(s))) return true;
        return lines.Take(5).Any(l => l.Contains(HeaderMarker));
    }
}

public class ReposFile
{
    public List<RepoConfig> Repos { get; set; } = new();
    public SyntheticRules Synthetic { get; set; } = new();
}

public class ApiRoutes
{
    public string ControllerSuffix { get; set; }
    public string ControllerToken { get; set; }
    public string ActionToken { get; set; } = "[action]";
    public List<string> RouteAttributes { get; set; } = new();
    public Dictionary<string, string> VerbAttributes { get; set; } = new();
    public List<string> ControllerBaseClasses { get; set; } = new();
}
public class RoutesFile { public ApiRoutes Api { get; set; } = new(); }

public class LayerRule { public string Match { get; set; } public string Kind { get; set; } public string Note { get; set; } }
public class TestsCsharp { public List<string> TestAttributes { get; set; } = new(); public List<string> TestDirMarkers { get; set; } = new(); public string MethodPattern { get; set; } }
public class TestsSql { public List<string> TestDirMarkers { get; set; } = new(); }
public class TestsConfig { public string AnnotationTag { get; set; } = "@covers"; public TestsCsharp Csharp { get; set; } = new(); public TestsSql Sql { get; set; } = new(); }
public class SqlNaming
{
    public string DefaultSchema { get; set; }
    public List<string> IgnoredNamePrefixes { get; set; } = new();
    public List<string> DynamicExecProcedures { get; set; } = new();
}
public class SqlAccess
{
    public List<string> CommandTypes { get; set; } = new();
    public string CommandTextMember { get; set; }
    public string CommandTypeMember { get; set; }
    public List<string> StoredProcedureMarkers { get; set; } = new();
}
public class NamingFile { public List<LayerRule> Layers { get; set; } = new(); public SqlNaming Sql { get; set; } = new(); public SqlAccess SqlAccess { get; set; } = new(); public TestsConfig Tests { get; set; } = new(); }

public static class Cfg
{
    private static readonly IDeserializer D = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance).IgnoreUnmatchedProperties().Build();

    public static T Load<T>(string file) => D.Deserialize<T>(File.ReadAllText(file));

    /// <summary>Loads repos.yml (the scanner view cdi writes from .cdi/config.yml) and resolves repo paths relative to the PoC root (parent of the config dir).</summary>
    public static (RepoConfig repo, SyntheticRules synth) Repo(string configDir, string repoName, string overridePath = null)
    {
        var rf = Load<ReposFile>(Path.Combine(configDir, "repos.yml"));
        var r = rf.Repos.FirstOrDefault(x => x.Name == repoName) ?? throw new Exception($"repo '{repoName}' not in repos.yml");
        var root = Path.GetFullPath(Path.Combine(configDir, ".."));
        r.AbsPath = Path.GetFullPath(overridePath ?? (Path.IsPathRooted(r.Path) ? r.Path : Path.Combine(root, r.Path)));
        return (r, rf.Synthetic);
    }
}
