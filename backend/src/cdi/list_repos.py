"""Print 'name plugin path' for each logical repo in .cdi/config.yml. Run from the target repository root (or pass --config / set CDI_CONFIG)."""
import sys
from cdi import config as C


def main(config=None):
    cfg = C.load(config)
    for r in C.scanner_view(cfg)["repos"]["repos"]:
        print(r["name"], r["plugin"], r["path"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
