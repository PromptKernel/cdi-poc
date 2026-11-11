"""Hunk -> node mapping: old side vs baseline locations, new side vs overlay locations."""
from impact import diff as D, mapper


def n(name, a, b, kind="METHOD", file="f.cs", repo="r"):
    return {"id": f"{repo}:{kind.lower()}:{name}", "kind": kind, "name": name, "repo": repo, "file": file, "location": {"line": a, "end_line": b}, "synthetic": False}


def ch(status="M", *hunks):
    return D.FileChange("f.cs", status, [D.Hunk(*h) for h in hunks])


def names(res):
    return {(m.node["name"], m.change, tuple(m.sides)) for m in res[0]}


def test_pure_deletion_inside_a_modified_file_maps_on_the_old_side():
    base = [n("A", 10, 20), n("B", 30, 40)]
    over = [n("A", 10, 17), n("B", 27, 37)]             # 3 lines deleted from A; B shifted up
    res = mapper.map_file(ch("M", (12, 3, 11, 0)), base, over)   # new side empty (new_len = 0)
    assert names(res) == {("A", "modified", ("old",))}
    assert res[1] is None


def test_pure_addition_maps_on_the_new_side_only():
    base = [n("A", 10, 20)]
    over = [n("A", 10, 23)]
    res = mapper.map_file(ch("M", (14, 0, 15, 3)), base, over)   # old side empty
    assert names(res) == {("A", "modified", ("new",))}


def test_modification_hits_both_sides():
    base, over = [n("A", 10, 20)], [n("A", 10, 21)]
    assert names(mapper.map_file(ch("M", (12, 2, 12, 3)), base, over)) == {("A", "modified", ("new", "old"))}


def test_old_side_is_compared_to_baseline_not_overlay_positions():
    """5 lines inserted ABOVE method A shift it from 10-20 to 15-25: A is NOT changed, and the inserted lines map to no node."""
    base, over = [n("A", 10, 20)], [n("A", 15, 25)]
    res = mapper.map_file(ch("M", (4, 0, 5, 5)), base, over)
    assert res[0] == [] and "no graph node" in res[1]


def test_new_side_is_compared_to_overlay_not_baseline_positions():
    """A edit at new lines 16-17 hits A at its NEW position 15-25 although the old position 10-20 would not contain line 16+ ... and vice versa."""
    base, over = [n("A", 10, 20)], [n("A", 15, 25)]
    res = mapper.map_file(ch("M", (4, 0, 5, 5), (18, 1, 23, 1)), base, over)
    assert names(res) == {("A", "modified", ("new", "old"))}


def test_deleting_a_whole_method_marks_it_removed():
    base, over = [n("A", 10, 20), n("B", 22, 30)], [n("A", 10, 20)]
    res = mapper.map_file(ch("M", (22, 9, 21, 0)), base, over)
    assert names(res) == {("B", "removed", ("old",))}


def test_adding_a_method_marks_it_added():
    base, over = [n("A", 10, 20)], [n("A", 10, 20), n("B", 22, 30)]
    res = mapper.map_file(ch("M", (21, 0, 22, 9)), base, over)
    assert names(res) == {("B", "added", ("new",))}


def test_file_deleted_all_baseline_nodes_removed_and_file_added_all_overlay_nodes_added():
    base = [n("A", 1, 5), n("B", 6, 9)]
    assert names(mapper.map_file(ch("D", (1, 9, 0, 0)), base, [])) == {("A", "removed", ("file",)), ("B", "removed", ("file",))}
    assert names(mapper.map_file(ch("A", (0, 0, 1, 9)), [], base)) == {("A", "added", ("file",)), ("B", "added", ("file",))}


def test_changed_file_without_a_node_is_reported_not_ignored():
    res = mapper.map_file(ch("M", (1, 1, 1, 1)), [n("A", 10, 20)], [n("A", 10, 20)])     # an import line
    assert res[0] == [] and res[1].startswith("no graph node")


def test_excluded_kinds_are_not_changed_objects():
    base = [n("req", 5, 6, kind="HTTP_REQUEST"), n("A", 1, 10)]
    res = mapper.map_file(ch("M", (5, 1, 5, 1)), base, base, excluded_kinds={"HTTP_REQUEST"})
    assert names(res) == {("A", "modified", ("new", "old"))}


def test_a_node_spanning_the_hunk_boundary_counts():
    res = mapper.map_file(ch("M", (20, 5, 20, 5)), [n("A", 10, 21)], [n("A", 10, 21)])
    assert len(res[0]) == 1


def test_parse_diff_handles_old_new_ranges_and_default_length():
    t = "diff --git a/x/f.sql b/x/f.sql\n--- a/x/f.sql\n+++ b/x/f.sql\n@@ -5,2 +4,0 @@\n-a\n-b\n@@ -9 +7,2 @@\n-c\n+d\n+e\n"
    (c,) = D.parse_diff(t, "x/")
    assert c.path == "f.sql"
    assert [(h.old_range, h.new_range) for h in c.hunks] == [((5, 6), None), ((9, 9), (7, 8))]


def test_is_scanned_uses_include_and_exclude_globs():
    assert D.is_scanned("src/a/b.ts", ["src/**/*.ts"], ["**/*.d.ts"])
    assert not D.is_scanned("src/b.d.ts", ["src/**/*.ts"], ["**/*.d.ts"])
    assert not D.is_scanned("README.md", ["**/*.sql"], [])
    assert D.is_scanned("a.sql", ["**/*.sql"], [])          # zero directories
