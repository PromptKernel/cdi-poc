"""Run the scanner that matches a logical repo's kind (config/repos.yml) and return its fragment. Used by the baseline runner and the impact engine."""
from __future__ import annotations
import json, os, pathlib, subprocess

KIND_SCANNER = {"frontend": "ts", "api": "cs", "sql": "sql"}


class ScanRunner:
    def __init__(self, tool_root, config_dir, work_dir):
        self.tool_root, self.config_dir, self.work = pathlib.Path(tool_root), pathlib.Path(config_dir), pathlib.Path(work_dir)
        self.env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
        if "DOTNET_ROOT" not in self.env and pathlib.Path("/opt/homebrew/opt/dotnet/libexec").is_dir():
            self.env["DOTNET_ROOT"] = "/opt/homebrew/opt/dotnet/libexec"
        self._built = False

    def build(self):
        if not self._built:
            for p in ("sql-scriptdom", "dotnet-roslyn"):
                subprocess.run(["dotnet", "build", "-nologo", "-v", "q", str(self.tool_root / "scanners" / p)], env=self.env, check=True, capture_output=True)
            self._built = True

    def scan(self, repo_cfg, repo_path, only_files=None):
        """repo_cfg: entry from repos.yml; repo_path: absolute folder of that logical repo (main tree or a worktree)."""
        self.build()
        self.work.mkdir(parents=True, exist_ok=True)
        out = self.work / f"scan_{repo_cfg['name']}.json"
        if out.exists():
            out.unlink()           # a single output file written by this module; not user data
        args = ["--config", str(self.config_dir), "--repo", repo_cfg["name"], "--out", str(out), "--repo-path", str(repo_path)]
        if only_files is not None:
            of = self.work / f"only_{repo_cfg['name']}.txt"
            of.write_text("\n".join(sorted(only_files)))
            args += ["--only", str(of)]
        kind = KIND_SCANNER[repo_cfg["kind"]]
        if kind == "ts":
            cmd = ["node", str(self.tool_root / "scanners/ts-morph/scan.mjs")] + args
        else:
            dll = {"cs": "dotnet-roslyn/bin/Debug/net10.0/CsScanner.dll", "sql": "sql-scriptdom/bin/Debug/net10.0/SqlScanner.dll"}[kind]
            cmd = ["dotnet", str(self.tool_root / "scanners" / dll)] + args
        r = subprocess.run(cmd, env=self.env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"scanner for {repo_cfg['name']} failed:\n{r.stdout}\n{r.stderr}")
        return json.loads(out.read_text())
