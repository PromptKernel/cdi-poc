"""Run the scanner plugin selected for a logical repo (`scanner.plugin` in .cdi/config.yml) and return its fragment.
Used by the baseline runner and the impact engine."""
from __future__ import annotations
import json, os, pathlib, subprocess
from cdi import config as C, plugins


def scanner_dir(config) -> pathlib.Path:
    """`config` is a scanner view folder (repos.yml, routes.yml, naming.yml) or anything cdi.config.load accepts."""
    p = pathlib.Path(config)
    if (p / "repos.yml").is_file():
        return p
    return C.materialize(C.load(p))


class ScanRunner:
    def __init__(self, tool_root, config, work_dir):
        self.tool_root, self.config_dir, self.work = pathlib.Path(tool_root), scanner_dir(config), pathlib.Path(work_dir)
        self.env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
        if "DOTNET_ROOT" not in self.env and pathlib.Path("/opt/homebrew/opt/dotnet/libexec").is_dir():
            self.env["DOTNET_ROOT"] = "/opt/homebrew/opt/dotnet/libexec"
        self._built = set()

    def build(self, plugin):
        if plugin.build_project and plugin.id not in self._built:
            subprocess.run(["dotnet", "build", "-nologo", "-v", "q", str(self.tool_root / "scanners" / plugin.build_project)],
                           env=self.env, check=True, capture_output=True)
        self._built.add(plugin.id)

    def scan(self, repo_cfg, repo_path, only_files=None):
        """repo_cfg: a repo entry (name, plugin); repo_path: absolute folder of that logical repo (main tree or a worktree)."""
        plugin = plugins.get(repo_cfg["plugin"])
        self.build(plugin)
        self.work.mkdir(parents=True, exist_ok=True)
        out = self.work / f"scan_{repo_cfg['name']}.json"
        if out.exists():
            out.unlink()           # a single output file written by this module; not user data
        args = ["--config", str(self.config_dir), "--repo", repo_cfg["name"], "--out", str(out), "--repo-path", str(repo_path)]
        if only_files is not None:
            of = self.work / f"only_{repo_cfg['name']}.txt"
            of.write_text("\n".join(sorted(only_files)))
            args += ["--only", str(of)]
        r = subprocess.run(plugin.command(self.tool_root, args), env=self.env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"scanner for {repo_cfg['name']} failed:\n{r.stdout}\n{r.stderr}")
        return json.loads(out.read_text())
