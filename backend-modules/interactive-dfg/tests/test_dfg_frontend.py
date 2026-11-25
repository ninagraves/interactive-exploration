"""Cross-check: the page applies the arc settings in the browser (`lib/dfgArcs.ts`), the notebooks
and tests in Python (`dfg/arcs.py`, `dfg/connectivity.py`). This test runs the TypeScript functions with Node on the
arcs the route sends and checks that they show exactly the arcs of `directly_follows_graph`.
The activity search (`lib/dfgActivitySearch.ts`) is checked on the running example in the same way.
Skipped if Node (22.6 or later, for TypeScript without a build step) is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ocelescope_module_interactive_dfg.dfg.graph import TypeSetting, directly_follows_graph, log_frames

from test_dfg import _pallet_example, every_activity

DFG_ARCS = Path(__file__).parents[3] / "frontend-modules" / "interactive-dfg" / "src" / "lib" / "dfgArcs.ts"
RUNNER = """
const { filterArcs } = await import(process.argv[2]);
const cases = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = cases.map(({ arcs, threshold, count, total, stay }) =>
  filterArcs(arcs, {
    threshold: (t) => threshold[t] ?? 100,
    count: (t) => count[t] ?? null,
    total,
    stayConnected: stay,
  }).shown.map((a) => [a.object_type, a.source ?? null, a.target ?? null, a.connecting]),
);
console.log(JSON.stringify(out));
"""

#: (variant threshold, arc threshold, arc count, stay connected[, total]) of the pallets (and, with
#: total, trucks) in the worked example; total = Arcs (display) in "general" mode.
CASES = [
    (60, 100, None, True),
    (60, 70, None, True),
    (60, 50, None, False),
    (60, 50, None, True),
    (60, 100, 3, False),
    (60, 100, 3, True),
    (100, 30, 4, True),
    (100, 0, None, True),
    (100, 12.5, 2, True),
    (100, 100, None, False, 5),
    (100, 100, None, True, 5),
    (100, 50, None, False, 3),
    (100, 50, None, True, 3),
    (100, 100, 2, False, 4),
]


def _node() -> str:
    """The Node executable, or skip the test."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if tuple(int(x) for x in version.split(".")[:2]) < (22, 6):
        pytest.skip(f"Node {version} cannot run TypeScript without a build step")
    return node


def test_frontend_arc_settings_match_python(tmp_path):
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet", "truck")
    inputs, expected = [], []
    for variants, threshold, count, stay, *rest in CASES:
        total = rest[0] if rest else None
        # With total: pallets and trucks, the pallets with their own count (if any), the trucks pooled.
        types = ["pallet", "truck"] if total is not None else ["pallet"]
        # What the route sends: all arcs of the included traces.
        base = directly_follows_graph(frames, [TypeSetting(object_type=t, variant_threshold=variants, arc_threshold=100) for t in types], activities=every, stay=False)
        inputs.append(
            {
                "arcs": [a.model_dump() for a in base.arcs],
                "threshold": {t: threshold for t in types},
                "count": {"pallet": count} if count is not None else {},
                "total": total,
                "stay": stay,
            }
        )
        setting = [
            TypeSetting(object_type=t, variant_threshold=variants, arc_threshold=threshold, arc_count=count if t == "pallet" else None)
            for t in types
        ]
        graph = directly_follows_graph(frames, setting, activities=every, stay=stay, arc_total=total)
        expected.append(sorted([a.object_type, a.source or "", a.target or "", a.connecting] for a in graph.arcs))
    runner = tmp_path / "runner.mjs"
    runner.write_text(RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri()], input=json.dumps(inputs), capture_output=True, text=True, check=True
    )
    shown = [sorted([t, s or "", g or "", c] for t, s, g, c in case) for case in json.loads(result.stdout)]
    for case, (got, want) in enumerate(zip(shown, expected, strict=True)):
        assert got == want, f"case {CASES[case]}"


NEEDED_RUNNER = """
const { neededArcThresholds } = await import(process.argv[2]);
const arcs = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = {};
for (const [t, m] of neededArcThresholds(arcs, Number(process.argv[3] ?? 0))) out[t] = Object.fromEntries(m);
console.log(JSON.stringify(out));
"""


def test_needed_projection_thresholds_match_python(tmp_path):
    """`neededArcThresholds` gives, per activity, the smallest whole Arcs (projection) value at which Python's
    `arc_share_filter` keeps an arc touching it (checked by trying every value from 1 to 100)."""
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet")
    base = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=100)], activities=every, stay=False)
    runner = tmp_path / "needed.mjs"
    runner.write_text(NEEDED_RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri()], input=json.dumps([a.model_dump() for a in base.arcs]), capture_output=True, text=True, check=True
    )
    needed = json.loads(result.stdout)["pallet"]
    expected = {}
    for alpha in range(100, 0, -1):
        setting = [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=alpha)]
        graph = directly_follows_graph(frames, setting, activities=every, stay=False)
        for a in graph.arcs:
            for activity in (a.source, a.target):
                if activity is not None:
                    expected[activity] = alpha
    assert needed == expected


def test_exact_projection_thresholds_match_python(tmp_path):
    """With 3 decimals, `neededArcThresholds` gives the value at which Python's `arc_share_filter` keeps an arc of the
    activity, and 0.001 less does not (Nina, 2026-11-18: shown in the unfold)."""
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet")
    base = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=100)], activities=every, stay=False)
    runner = tmp_path / "needed.mjs"
    runner.write_text(NEEDED_RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri(), "3"], input=json.dumps([a.model_dump() for a in base.arcs]), capture_output=True, text=True, check=True
    )
    needed = json.loads(result.stdout)["pallet"]

    def drawn(alpha: float) -> set[str]:
        setting = [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=alpha)]
        arcs = directly_follows_graph(frames, setting, activities=every, stay=False).arcs
        return {x for a in arcs for x in (a.source, a.target) if x is not None}

    assert any(round(v) != v for v in needed.values())
    for activity, value in needed.items():
        assert activity in drawn(value)
        if value > 0.001:
            assert activity not in drawn(round(value - 0.001, 3))


DFG_SEARCH = DFG_ARCS.parent / "dfgActivitySearch.ts"
SEARCH_RUNNER = """
const { activitiesOf, chipCount, matchingObjectTypes, activityMatches } = await import(process.argv[2]);
const { options, types, cases } = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = {
  lists: cases.map((picked) => activitiesOf(options, picked).map((o) => [o.activity, chipCount(o, picked)])),
  all: activitiesOf(options, []).map((o) => o.activity),
  hits: Object.fromEntries(["o", "co", "COI", "coil", " slab ", "Coil", "x"].map((q) => [q, matchingObjectTypes(types, q)])),
  short: ["bo", "box", "BOX ", "boxe"].map((q) => matchingObjectTypes(["boxes", "box"], q)),
  names: options.filter((o) => activityMatches(o, " TRUCK")).map((o) => o.activity),
};
console.log(JSON.stringify(out));
"""

#: Picked object type chips (they stack) on the running example.
CHIP_CASES = [["coil"], ["slab"], ["coil", "slab"], ["slab", "coil"]]


def test_activity_search_chips_list_the_activities_of_all_picked_types(tmp_path, ocel):
    """Object type chips: every activity that all picked types are involved in, by the smallest of their events
    (`chipCount`), ties by events with an object of a selected type, events in the log, name. Type names match
    case-insensitively by a part from 4 letters on, below only by their full name; activity names by a part."""
    node = _node()
    graph = directly_follows_graph(log_frames(ocel))
    runner = tmp_path / "search.mjs"
    runner.write_text(SEARCH_RUNNER)
    payload = {
        "options": [o.model_dump() for o in graph.activity_options],
        "types": [t.object_type for t in graph.object_types],
        "cases": CHIP_CASES,
    }
    result = subprocess.run([node, str(runner), DFG_SEARCH.as_uri()], input=json.dumps(payload), capture_output=True, text=True, check=True)
    out = json.loads(result.stdout)

    for picked, got in zip(CHIP_CASES, out["lists"], strict=True):
        events = {
            o.activity: min(next((x.events for x in o.object_types if x.object_type == t), 0) for t in picked)
            for o in graph.activity_options
        }
        expected = sorted(
            (o for o in graph.activity_options if events[o.activity] > 0),
            key=lambda o: (-events[o.activity], -o.selected_events, -o.log_events, o.activity),
        )
        assert got == [[o.activity, events[o.activity]] for o in expected], picked
    coil = [["crane move", 4], ["quality check", 4], ["load truck", 2], ["unload truck", 2], ["cut", 1], ["label", 1], ["roll", 1]]
    assert out["lists"][0] == coil
    assert [a for a, _ in out["lists"][1]] == ["cast slab", "inspect slab", "roll"]
    assert out["lists"][2] == out["lists"][3] == [["roll", 1]]
    assert out["all"] == [o.activity for o in graph.activity_options]

    assert out["hits"] == {"o": [], "co": [], "COI": [], "coil": ["coil"], " slab ": ["slab"], "Coil": ["coil"], "x": []}
    assert out["short"] == [[], ["box"], ["box"], ["boxes"]]
    assert out["names"] == [o.activity for o in graph.activity_options if "truck" in o.activity]
