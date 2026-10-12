"""A run recorded as a line has no recorded graph, but each receipt records the receipts it read.
Those reads are its links: listed in the graph's table, and drawn as lines between boxes next to
each other in the record's order -- across a wrap, down from one row and into the next. No line is
drawn where no read is recorded. On a narrow screen the same boxes are a list in reading order,
each saying whether it reads the box before it.
"""
from __future__ import annotations

import re

from onetrace_console.viewer.graph import GraphNode, as_list, lay_out, render


def _line(n: int, reads_previous: bool = True, skip: int | None = None) -> list[GraphNode]:
    names = [f"s{i}" for i in range(1, n + 1)]
    return [GraphNode(node_id=name, name=name, index=i, href=f"#step-{i}",
                      reads=((names[i - 2],) if i > 1 and reads_previous and i != skip else ()))
            for i, name in enumerate(names, start=1)]


def link_problems(nodes: list[GraphNode], layout) -> list[str]:
    """The drawn links against the receipts' recorded reads."""
    order = [n.node_id for n in sorted(nodes, key=lambda n: n.index)]
    want = {(a, b) for a, b in zip(order, order[1:])
            if a in next(n for n in nodes if n.node_id == b).reads}
    got = set(layout.links)
    out = [f"drawn with no recorded read: {p}" for p in sorted(got - want)]
    out += [f"a recorded read not drawn: {p}" for p in sorted(want - got)]
    return out


def test_a_line_draws_a_link_only_where_a_read_is_recorded(examined):
    nodes = _line(6, skip=4)
    layout = lay_out(nodes, None, wrap=4)
    examined(len(nodes), "nodes")
    assert link_problems(nodes, layout) == []
    assert ("s3", "s4") not in layout.links, "s4 records no read of s3"
    assert set(layout.recorded) == {(a, b) for a, b in layout.links}, "every read listed"


def test_a_link_across_a_wrap_goes_down_and_into_the_next_row(examined):
    nodes = _line(5)
    layout = lay_out(nodes, None, wrap=4)
    svg = render(nodes, None, wrap=4)
    paths = re.findall(r'<path class="link" d="([^"]+)"', svg)
    examined(len(paths), "links drawn")
    assert len(paths) == 4
    elbow = [d for d in paths if d.count("L") == 3]
    assert len(elbow) == 1, paths
    rows = {b.key: b.row for b in layout.boxes}
    assert rows["s4"] == 0 and rows["s5"] == 1


def test_no_read_recorded_no_line(examined):
    nodes = _line(5, reads_previous=False)
    examined(1, "line")
    assert lay_out(nodes, None, wrap=4).links == ()
    assert '<path class="link"' not in render(nodes, None, wrap=4)


def test_the_narrow_list_keeps_every_box_in_order_and_says_what_it_reads(examined):
    nodes = _line(6, skip=4)
    html = as_list(lay_out(nodes, None, wrap=4))
    items = re.findall(r'<li data-reads-previous="(yes|no)"[^>]*><a href="#step-(\d+)">', html)
    examined(len(items), "list items")
    assert [int(i) for _, i in items] == [1, 2, 3, 4, 5, 6]
    assert [r for r, _ in items] == ["no", "yes", "yes", "no", "yes", "yes"]


def test_sabotage_an_invented_or_missing_link_is_named(examined):
    from dataclasses import replace
    nodes = _line(5, skip=3)
    layout = lay_out(nodes, None, wrap=4)
    invented = replace(layout, links=layout.links + (("s2", "s3"),))
    missing = replace(layout, links=layout.links[1:])
    examined(2, "planted layouts")
    assert any("no recorded read" in p for p in link_problems(nodes, invented))
    assert any("not drawn" in p for p in link_problems(nodes, missing))


def test_the_record_s_reads_reach_the_graph(examined):
    """The model reads each receipt's `receipt:<node id>` inputs into its node, and nothing else."""
    from types import SimpleNamespace

    from onetrace_console.viewer.model import _graph_nodes
    steps = [SimpleNamespace(data={"stage": {"name": "a"}, "inputs": [{"name": "q.json"}]},
                             manifest_stage="a", manifest_index="1"),
             SimpleNamespace(data={"stage": {"name": "b"}, "inputs": [
                 {"name": "receipt:a"}, {"name": "a.json"}, {"name": 7}]},
                 manifest_stage="b", manifest_index="2")]
    nodes = _graph_nodes(SimpleNamespace(steps=steps), ())
    examined(len(nodes), "nodes")
    assert [n.reads for n in nodes] == [(), ("a",)]


def test_the_demo_run_pages_wrap_and_draw_their_recorded_reads(tmp_path_factory, examined):
    """Every straight-line run page of the public demo: more than four stages wrap onto a second row;
    its boxes are all drawn; and its lines are as many as its consecutive recorded reads."""
    import json

    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("demo") / "demo"
    build_public(folder)
    store, pages = Store(folder / "store" / "store"), folder / "store" / "pages"
    checked = 0
    for run in store.runs():
        page = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        if 'data-section="graph-linear"' not in page:
            continue
        rd = folder / "runs" / run.run_id / "receipts"
        receipts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(rd.glob("*.json"))]
        ids = [r["stage"]["name"] + (f'#{r["stage"]["instance"]}' if r["stage"].get("instance") else "")
               for r in receipts]
        reads = [{i["name"][8:] for i in r.get("inputs", []) if i["name"].startswith("receipt:")}
                 for r in receipts]
        names = [r["stage"]["name"] for r in receipts]
        folded = len(set(names)) != len(names)
        svg = re.search(r'<svg class="graph".*?</svg>', page, re.S).group(0)
        ys = set(re.findall(r'<rect class="node" x="\d+" y="(\d+)"', svg))
        boxes = len(re.findall(r'<rect class="node"', svg))
        assert boxes == len(set(names)), run.run_id
        if boxes > 4:
            assert len(ys) > 1, f"{run.run_id}: one row"
        if not folded:
            want = sum(a in rb for a, rb in zip(ids, reads[1:]))
            assert svg.count('<path class="link"') == want, run.run_id
        assert '<ol class="graph-list">' in page
        checked += 1
    examined(checked, "straight-line run pages")
    assert checked > 10
