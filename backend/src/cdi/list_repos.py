"""Print 'name kind path' for each logical repo in config/repos.yml (used by pipeline scripts). Run from the target repository root."""
import pathlib, yaml


def main(root=None):
    root = pathlib.Path(root or pathlib.Path.cwd())
    for r in yaml.safe_load((root / "config/repos.yml").read_text())["repos"]:
        print(r["name"], r["kind"], r["path"])


if __name__ == "__main__":
    main()
