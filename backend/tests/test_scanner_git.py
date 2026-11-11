"""commit_id = git log -1 -- <logical repo folder>; dirty check is limited to that folder."""
import pathlib


def test_commit_id_is_last_commit_touching_the_folder(project, full):
    for repo, folder in (("web", "samples/web"), ("api", "samples/api"), ("db", "samples/db")):
        assert full[repo]["commit_id"] == project.head_for(folder)
        assert {e["commit_id"] for e in full[repo]["edges"]} == {full[repo]["commit_id"]}


def test_dirty_file_inside_repo_folder_is_refused(project):
    p = project.path / "samples/db/untracked_tmp.txt"
    p.write_text("x")
    try:
        r, frag = project.scan("db", "dirty_db.json", check=False)
        assert r.returncode != 0 and frag is None
        assert "uncommitted changes" in (r.stdout + r.stderr)
    finally:
        p.unlink()


def test_dirty_file_in_other_folder_is_ignored(project):
    p = project.path / "samples/web/untracked_tmp.txt"   # dirty, but NOT in the db logical repo
    p.write_text("x")
    try:
        r, frag = project.scan("db", "other_db.json", check=False)
        assert r.returncode == 0 and frag["commit_id"] == project.head_for("samples/db")
        r2, _ = project.scan("web", "other_web.json", check=False)
        assert r2.returncode != 0, "the dirty file is inside the web folder"
    finally:
        p.unlink()


def test_modified_tracked_file_is_refused_for_every_scanner(project):
    targets = {"api": "samples/api/Program.cs", "web": "samples/web/src/main.ts", "db": "samples/db/README.md"}
    for repo, rel in targets.items():
        f = project.path / rel
        orig = f.read_text()
        f.write_text(orig + "\n// edit\n")
        try:
            r, _ = project.scan(repo, f"mod_{repo}.json", check=False)
            assert r.returncode != 0, f"{repo} scanner scanned a modified tree"
        finally:
            f.write_text(orig)
