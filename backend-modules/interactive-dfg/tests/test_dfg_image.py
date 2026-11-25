"""Tests of the download as an image (`lib/dfgDrawing.ts`, `lib/dfgDownload.ts`): the running example's graph is laid
out with the page's own ELK layout (`lib/dfgLayout.ts`) and drawn as a scene with Node; its SVG must be valid XML with
every node, arc, arrow head and label inside the image, and its PDF a vector PDF (no embedded image).
Skipped if Node (22.6 or later) or the frontend packages (`pnpm install`) are missing.
"""

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ocelescope_module_interactive_dfg.dfg.graph import directly_follows_graph, log_frames

from test_dfg_frontend import _node

LIB = Path(__file__).parents[3] / "frontend-modules" / "interactive-dfg" / "src" / "lib"
SVG = "{http://www.w3.org/2000/svg}"

#: The page's TypeScript imports its own files without extension (bundler style); Node needs ".ts" added.
RESOLVE_TS = """
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`
export async function resolve(specifier, context, next) {
  try { return await next(specifier, context); }
  catch (error) { if (specifier.startsWith(".") && !specifier.endsWith(".ts")) return next(specifier + ".ts", context); throw error; }
}`));
"""

RUNNER = (
    RESOLVE_TS
    + """
const [lib, direction, arcLabel, compact, legend] = process.argv.slice(2);
const { layoutGraph } = await import(lib + "/dfgLayout.ts");
const { graphScene, sceneSvg } = await import(lib + "/dfgDrawing.ts");
const { scenePdf } = await import(lib + "/dfgDownload.ts");
const graph = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const layout = await layoutGraph(graph, direction, arcLabel, compact === "true");
// The second object type gets a colour with alpha, as the paler types on the page.
const colours = new Map(graph.object_types.map((t, i) => [t.object_type, i === 0 ? "#006165" : "#0098a18c"]));
const drawing = {
  nodes: layout.nodes,
  arcs: layout.arcs.map((a) => ({ ...a, colour: colours.get(a.objectType), width: 2 })),
  colours,
  arcLabel,
};
const scene = graphScene(drawing, { legend: legend === "true" });
const pdf = scenePdf(scene).output();
console.log(JSON.stringify({ svg: sceneSvg(scene), width: scene.width, height: scene.height, pdf, nodes: layout.nodes, arcs: layout.arcs }));
"""
)

DOWNLOAD_RUNNER = (
    RESOLVE_TS
    + """
const { exportFileName, pngScale } = await import(process.argv[2] + "/dfgDownload.ts");
console.log(JSON.stringify({
  name: exportFileName("running example", "pdf", new Date(2026, 10, 20)),
  unnamed: exportFileName(undefined, "png", new Date(2026, 0, 5)),
  small: pngScale(1000, 600),
  wide: pngScale(10000, 100),
  large: pngScale(20000, 12000),
}));
"""
)


def _frontend_packages() -> None:
    """Skip if `pnpm install` has not run (the layout needs elkjs, the PDF jspdf)."""
    modules = LIB.parents[1] / "node_modules"
    if not (modules / "elkjs").exists() or not (modules / "jspdf").exists():
        pytest.skip("Frontend packages not installed (pnpm install)")


def _run(tmp_path, script: str, *args: str, stdin: str = "") -> dict:
    """Run a Node script with the page's lib folder as first argument and return its JSON output."""
    node = _node()
    _frontend_packages()
    runner = tmp_path / "runner.mjs"
    runner.write_text(script)
    result = subprocess.run(
        [node, str(runner), LIB.as_uri(), *args], input=stdin, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def graph(ocel):
    """The running example's graph as the route sends it (default selection, all arcs)."""
    return directly_follows_graph(log_frames(ocel)).model_dump()


@pytest.mark.parametrize(
    ("direction", "arc_label", "compact", "legend"),
    [("RIGHT", "count", False, True), ("DOWN", "objects", True, False)],
)
def test_scene_shows_every_node_arc_and_label(tmp_path, graph, direction, arc_label, compact, legend):
    """One box per activity, one line, arrow head and label per arc, every name and label as text, colours with alpha
    blended onto white, everything inside the image; the PDF has no embedded image."""
    out = _run(tmp_path, RUNNER, direction, arc_label, str(compact).lower(), str(legend).lower(), stdin=json.dumps(graph))
    root = ET.fromstring(out["svg"])
    assert root.tag == f"{SVG}svg"
    assert (int(root.get("width")), int(root.get("height"))) == (out["width"], out["height"])

    activities = [n for n in out["nodes"] if n["data"]["kind"] == "activity"]
    terminals = [n for n in out["nodes"] if n["data"]["kind"] != "activity"]
    arcs = root.findall(f".//{SVG}g[@class='arc']")
    assert len(arcs) == len(out["arcs"]) == len(graph["arcs"])
    for arc in arcs:
        paths = arc.findall(f"{SVG}path")
        # Hover line, visible line, arrow head (filled).
        assert len(paths) == 3 and paths[2].get("fill") not in (None, "none")
    labels = sorted(t.text for arc in arcs for t in arc.iter(f"{SVG}text"))
    assert labels == sorted(a["label"] for a in out["arcs"])
    nodes = root.findall(f".//{SVG}g[@class='node']")
    assert len(nodes) == len(out["nodes"])
    assert sum(1 for g in nodes if g.find(f"{SVG}rect[@rx='4']") is not None) == len(activities) == len(graph["activities"])
    texts = {t.text for t in root.iter(f"{SVG}text")}
    assert {line for n in activities for line in n["data"]["lines"]} <= texts
    assert {n["data"]["objectType"] for n in terminals} <= texts
    assert ("Object types:" in texts) == legend
    assert not re.search(r'"#[0-9a-fA-F]{8}"', out["svg"])

    # Every shape lies inside the image.
    for element in root.iter():
        for attribute in ("x", "cx"):
            if element.get(attribute) is not None and element.tag != f"{SVG}svg":
                assert 0 <= float(element.get(attribute)) <= out["width"]
        for attribute in ("y", "cy"):
            if element.get(attribute) is not None and element.tag != f"{SVG}svg":
                assert 0 <= float(element.get(attribute)) <= out["height"]
    for path in root.iter(f"{SVG}path"):
        for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", path.get("d")):
            assert 0 <= float(x) <= out["width"] and 0 <= float(y) <= out["height"]

    pdf = out["pdf"]
    assert pdf.startswith("%PDF") and pdf.count("/Type /Page\n") + pdf.count("/Type /Page ") >= 1
    assert "/Subtype /Image" not in pdf


def test_file_name_and_png_scale(tmp_path):
    """File name "dfg_<log name>_<date>.<format>"; PNG at 4x, smaller for very large graphs."""
    out = _run(tmp_path, DOWNLOAD_RUNNER)
    assert out["name"] == "dfg_running_example_2026-11-20.pdf"
    assert out["unnamed"] == "dfg_2026-01-05.png"
    assert out["small"] == 4
    assert out["wide"] == pytest.approx(1.6)
    assert 20000 * 12000 * out["large"] ** 2 == pytest.approx(120e6)
