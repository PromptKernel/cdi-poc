"""Scanner plugin registry. A plugin knows how to build and run one scanner and which files it handles by default.

A target repository's `.cdi/config.yml` selects a plugin per logical repo (`scanner: {plugin: <id>, include: [...], exclude: [...]}`);
the globs choose which files that plugin reads. New scanners register here; nothing else in the tool names a scanner."""
from __future__ import annotations
from dataclasses import dataclass
import pathlib

DOTNET_TFM = "net10.0"


@dataclass(frozen=True)
class ScannerPlugin:
    id: str
    layer: str                       # frontend | api | sql: the architectural layer its nodes belong to
    description: str
    runtime: str                     # dotnet | node
    entry: str                       # path under backend/scanners/
    build_project: str | None        # scanners/<dir> to `dotnet build` first, or None
    default_include: tuple
    default_exclude: tuple

    def command(self, tool_root, args: list[str]) -> list[str]:
        base = pathlib.Path(tool_root) / "scanners"
        return [self.runtime, str(base / self.entry)] + list(args)


REGISTRY: dict[str, ScannerPlugin] = {}


def register(p: ScannerPlugin):
    if p.id in REGISTRY:
        raise ValueError(f"scanner plugin {p.id!r} already registered")
    REGISTRY[p.id] = p
    return p


def get(plugin_id: str) -> ScannerPlugin:
    try:
        return REGISTRY[plugin_id]
    except KeyError:
        raise KeyError(f"unknown scanner plugin {plugin_id!r}; registered: {sorted(REGISTRY)}") from None


register(ScannerPlugin("dotnet-roslyn", "api", "C# (Roslyn): controllers, methods, DI, ADO.NET stored-procedure calls, tests", "dotnet",
                       f"dotnet-roslyn/bin/Debug/{DOTNET_TFM}/CsScanner.dll", "dotnet-roslyn", ("**/*.cs",), ("**/bin/**", "**/obj/**")))
register(ScannerPlugin("ts-morph", "frontend", "TypeScript (ts-morph): components, services, HTTP requests, specs", "node",
                       "ts-morph/scan.mjs", None, ("src/**/*.ts",), ("**/node_modules/**", "**/*.d.ts")))
register(ScannerPlugin("sql-scriptdom", "sql", "T-SQL (ScriptDom): procedures, views, tables, references, SQL tests", "dotnet",
                       f"sql-scriptdom/bin/Debug/{DOTNET_TFM}/SqlScanner.dll", "sql-scriptdom", ("**/*.sql",), ()))
