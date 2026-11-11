using System.Text.Json;
using System.Text.Json.Serialization;

namespace Graph.Common;

public class Location
{
    [JsonPropertyName("line")] public int Line { get; set; }
    [JsonPropertyName("column")] public int? Column { get; set; }
    [JsonPropertyName("end_line")] public int? EndLine { get; set; }
    [JsonPropertyName("end_column")] public int? EndColumn { get; set; }
}

public class Node
{
    [JsonPropertyName("id")] public string Id { get; set; }
    [JsonPropertyName("kind")] public string Kind { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; }
    [JsonPropertyName("repo")] public string Repo { get; set; }
    [JsonPropertyName("file")] public string File { get; set; }
    [JsonPropertyName("location")] public Location Location { get; set; }
    [JsonPropertyName("synthetic")] public bool Synthetic { get; set; }
    [JsonPropertyName("attrs")] public Dictionary<string, object> Attrs { get; set; }
}

public class Edge
{
    [JsonPropertyName("id")] public string Id { get; set; }
    [JsonPropertyName("type")] public string Type { get; set; }
    [JsonPropertyName("source")] public string Source { get; set; }
    [JsonPropertyName("target")] public string Target { get; set; }
    [JsonPropertyName("source_file")] public string SourceFile { get; set; }
    [JsonPropertyName("location")] public Location Location { get; set; }
    [JsonPropertyName("analysis_method")] public string AnalysisMethod { get; set; }
    [JsonPropertyName("confidence")] public string Confidence { get; set; }
    [JsonPropertyName("commit_id")] public string CommitId { get; set; }
    [JsonPropertyName("repo")] public string Repo { get; set; }
    [JsonPropertyName("synthetic")] public bool Synthetic { get; set; }
    [JsonPropertyName("reason")] public string Reason { get; set; }
    [JsonPropertyName("evidence")] public string Evidence { get; set; }
    [JsonPropertyName("attrs")] public Dictionary<string, object> Attrs { get; set; }
}

public class ScannerInfo
{
    [JsonPropertyName("name")] public string Name { get; set; }
    [JsonPropertyName("version")] public string Version { get; set; }
}

public class Fragment
{
    [JsonPropertyName("schema_version")] public string SchemaVersion { get; set; } = "1.0";
    [JsonPropertyName("repo")] public string Repo { get; set; }
    [JsonPropertyName("commit_id")] public string CommitId { get; set; }
    [JsonPropertyName("scanned_at")] public string ScannedAt { get; set; }
    [JsonPropertyName("scanner")] public ScannerInfo Scanner { get; set; }
    [JsonPropertyName("files_scanned")] public int FilesScanned { get; set; }
    [JsonPropertyName("nodes")] public List<Node> Nodes { get; set; } = new();
    [JsonPropertyName("edges")] public List<Edge> Edges { get; set; } = new();
}
