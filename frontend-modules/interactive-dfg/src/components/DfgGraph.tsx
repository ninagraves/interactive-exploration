// The drawing of the directly-follows graph: ELK layout (lib/dfgLayout.ts), rendered with React Flow so that
// it can be panned and zoomed, and its nodes dragged (the arcs follow; Nina, 2026-11-15). The download button at its
// top right saves it as PDF, SVG, HTML or PNG (lib/dfgDrawing.ts, lib/dfgDownload.ts). Documented in
// docs/pages/interactive-dfg.md.
import { ActionIcon, Alert, Box, Checkbox, Group, Loader, Menu, Stack, Text, Tooltip } from "@mantine/core";
import {
  applyNodeChanges,
  BaseEdge,
  Controls,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  type Node,
  type NodeChange,
  type NodeProps,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import { DownloadIcon } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DirectlyFollowsGraph } from "../api/interactiveDfg";
import { downloadDrawing, IMAGE_FORMATS, type ImageFormat } from "../lib/dfgDownload";
import type { Drawing } from "../lib/dfgDrawing";
import {
  type ActivityNodeData,
  type ArcLabel,
  type Direction,
  type LaidOutArc,
  type Layout,
  layoutGraph,
  SIZES,
  type TerminalNodeData,
} from "../lib/dfgLayout";
import { num } from "../lib/format";
import { useKeptViewport } from "../lib/keptView";
import { keep, recall, sameInputs } from "../lib/pageState";

type NodeData = (ActivityNodeData | TerminalNodeData) & { colours: Map<string, string> };
type ArcData = LaidOutArc & { colour: string; width: number };

/** Invisible handles: React Flow needs them to draw an edge, the path itself comes from ELK. */
const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
    <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
  </>
);

/** Hover text of an activity node: frequency, events in the log, and the object types involved. */
const activityTooltip = (d: ActivityNodeData) => (
  <Stack gap={2}>
    <Text size="xs" fw={600}>{d.activity}</Text>
    <Text size="xs">
      {num(d.events)} events shown{d.logEvents !== d.events ? ` (of ${num(d.logEvents)} in the log)` : ""}
    </Text>
    {d.involved.map((t) => (
      <Text size="xs" key={t.objectType}>
        {t.objectType}{t.selected ? "" : " (not selected)"}: {num(t.events)} events, {num(t.objects)} objects
      </Text>
    ))}
    <Text size="xs" c="dimmed">Right click: copy the name · double click: deselect it for every object type</Text>
  </Stack>
);

/** Activity node: full name (wrapped, never cut), below it the frequency followed by a circle per involved type that is not selected. */
const ActivityNode = memo(({ data }: NodeProps<Node<NodeData>>) => {
  const d = data as ActivityNodeData & { colours: Map<string, string> };
  const circles = d.involved.filter((t) => !t.selected);
  return (
    <Tooltip label={activityTooltip(d)} withinPortal openDelay={300} multiline>
      <Box
        style={{
          width: d.width,
          height: d.height,
          padding: `${SIZES.padY}px ${SIZES.padX}px`,
          border: "1px solid var(--mantine-color-gray-7)",
          borderRadius: 4,
          background: "var(--mantine-color-body)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 0,
          boxSizing: "border-box",
        }}
      >
        <Handles />
        <Box style={{ fontSize: SIZES.nameFont, lineHeight: `${SIZES.nameLine}px`, fontWeight: d.nameWeight, textAlign: "center" }}>
          {d.lines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </Box>
        <Group gap={SIZES.circleGap} wrap="nowrap" align="center" justify="center">
          <Box style={{ fontSize: SIZES.frequencyFont, lineHeight: `${SIZES.frequencyFont + 3}px`, opacity: 0.7, marginRight: circles.length ? SIZES.circleGap : 0 }}>
            {num(d.events)}
          </Box>
          {circles.map((t) => (
            <Tooltip key={t.objectType} label={`${t.objectType}: ${num(t.events)} of ${num(d.events)} events, ${num(t.objects)} objects`} withinPortal>
              <Box
                style={{
                  width: SIZES.circle,
                  height: SIZES.circle,
                  borderRadius: "50%",
                  background: d.colours.get(t.objectType),
                  boxShadow: "0 0 0 0.5px var(--mantine-color-gray-6)",
                  flexShrink: 0,
                }}
              />
            </Tooltip>
          ))}
        </Group>
      </Box>
    </Tooltip>
  );
});

/** Start node (triangle) or end node (square) of an object type, filled with its colour, named below. */
const TerminalNode = memo(({ data }: NodeProps<Node<NodeData>>) => {
  const d = data as TerminalNodeData & { colours: Map<string, string> };
  const colour = d.colours.get(d.objectType);
  return (
    <Box style={{ width: d.width, height: d.height, position: "relative" }}>
      <Handles />
      <svg width={d.width} height={d.height} style={{ display: "block" }} role="img" aria-label={`${d.kind} ${d.objectType}`}>
        <circle cx={d.width / 2} cy={d.height / 2} r={d.width / 2 - 1} fill={colour} stroke="var(--mantine-color-text)" strokeWidth={1} />
        {d.kind === "start" ? (
          <path d={`M ${d.width * 0.4} ${d.height * 0.3} L ${d.width * 0.7} ${d.height / 2} L ${d.width * 0.4} ${d.height * 0.7} Z`} fill="white" />
        ) : (
          <rect x={d.width * 0.33} y={d.height * 0.33} width={d.width * 0.34} height={d.height * 0.34} fill="white" />
        )}
      </svg>
      <Box
        style={{
          position: "absolute",
          top: d.height + 1,
          left: "50%",
          transform: "translateX(-50%)",
          fontSize: SIZES.smallFont,
          opacity: 0.8,
          whiteSpace: "nowrap",
        }}
      >
        {d.objectType}
      </Box>
    </Box>
  );
});

/**
 * Arc: ELK's route in the object type's colour, with a small plain label (count or objects) that interrupts the line.
 * Hovering the line or the label shows its numbers and, for an arc shown only because of "Stay connected", says so
 * (drawn like every other arc; Nina, 2026-11-17).
 */
const ArcEdge = memo(({ id, data, markerEnd }: EdgeProps<Edge<ArcData>>) => {
  if (!data?.path) return null;
  const position = data.labelPosition;
  const hint = `${data.objectType}: ${num(data.count)} traversals, ${num(data.objects)} objects${data.connecting ? " · only kept to stay connected (Arcs (projection) or Arcs (display) would hide it)" : ""}`;
  return (
    <>
      <BaseEdge
        id={id}
        path={data.path}
        markerEnd={markerEnd}
        interactionWidth={12}
        style={{ stroke: data.colour, strokeWidth: data.width }}
      />
      {/* Hover area along the line with the same hint as the label (the browser's own tooltip). */}
      <path d={data.path} fill="none" stroke="transparent" strokeWidth={12} style={{ pointerEvents: "stroke" }}>
        <title>{hint}</title>
      </path>
      {position && (
        <EdgeLabelRenderer>
          <Tooltip label={hint} withinPortal>
            <Box
              className="nodrag nopan"
              style={{
                position: "absolute",
                transform: `translate(-50%, -50%) translate(${position.x}px, ${position.y}px)`,
                fontSize: SIZES.smallFont,
                lineHeight: `${SIZES.smallFont + 2}px`,
                padding: "0 2px",
                borderRadius: 3,
                background: "var(--mantine-color-body)",
                pointerEvents: "all",
              }}
            >
              {data.label}
            </Box>
          </Tooltip>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

/** Grey of start and end arcs. */
const GREY = "#9aa0a6";

/**
 * Colour of an arc: grey from a start node and to an end node (Nina, 2026-11-14; the start and end nodes carry the
 * type's colour), otherwise its object type's colour.
 *
 * Example: the arc start:coil → crane move is grey; crane move → load truck of coil has coil's colour.
 *
 * @param arc The arc's object type and node ids.
 * @param colours Colour per object type.
 * @returns The colour.
 */
export const arcColour = (arc: { objectType: string; source: string; target: string }, colours: Map<string, string>) =>
  arc.source.startsWith("start:") || arc.target.startsWith("end:") ? GREY : (colours.get(arc.objectType) ?? GREY);

/** The legend, in grey above the graph. */
const Legend = () => (
  <Text fz={11} lh={1.3} c="dimmed">
    ▶ / ■ in a circle: start / end of an object type (named below; arcs from and to them are grey) · coloured line:
    directly-follows arc of a selected object type (thicker = more traversals) · number on an arc: traversals or objects ·
    hover an arc: its numbers, and whether it is only kept to stay connected · number in an activity: its events on the included traces · small circle on an
    activity: an unselected object type involved in these events · double click on an activity: deselect it · right click on an activity: copy its name · drag a node to
    move it (the arcs follow; positions reset when a setting changes)
  </Text>
);

const NODE_TYPES = { activity: ActivityNode, start: TerminalNode, end: TerminalNode };
const EDGE_TYPES = { arc: ArcEdge };

/** Stroke width of an arc: 1.2 to 4 px, by the square root of its traversals relative to the largest arc of its type. */
const strokeWidth = (count: number, max: number) => 1.2 + 2.8 * Math.sqrt(count / Math.max(max, 1));

/** React Flow nodes and edges of a layout. */
const toFlow = (layout: Layout, colours: Map<string, string>) => {
  const maxCount = new Map<string, number>();
  for (const a of layout.arcs) maxCount.set(a.objectType, Math.max(maxCount.get(a.objectType) ?? 0, a.count));
  const nodes: Node<NodeData>[] = layout.nodes.map((n) => ({
    id: n.id,
    type: n.data.kind,
    position: { x: n.x, y: n.y },
    data: { ...n.data, colours },
    draggable: true,
    connectable: false,
  }));
  const edges: Edge<ArcData>[] = layout.arcs.map((a) => {
    const colour = arcColour(a, colours);
    return {
      id: a.id,
      source: a.source,
      target: a.target,
      type: "arc",
      data: { ...a, colour, width: strokeWidth(a.count, maxCount.get(a.objectType) ?? 1) },
      // React Flow draws the arrow in a 20-unit box of which it fills 5: 30 px gives an arrow of about 8 px, whatever the stroke width.
      markerEnd: { type: MarkerType.ArrowClosed, color: colour, width: 30, height: 30, markerUnits: "userSpaceOnUse" },
    };
  });
  return { nodes, edges };
};

type Offset = { x: number; y: number };

/**
 * Bend an ELK path to dragged nodes: its first point moves with the source node, its last point with the target
 * node, and every point in between by the share of both given by its position along the path (so a path of a
 * self-loop, or of two nodes moved together, is simply shifted).
 * Example: "M 0,0 C 10,0 20,0 30,0" with the target moved by (0, 30) gives "M 0,0 C 10,10 20,20 30,30".
 *
 * @param path SVG path of absolute "x,y" points (`sectionPath` in lib/dfgLayout.ts).
 * @param source, target Offsets of the source and target nodes from their laid-out positions.
 * @returns The bent path.
 */
export const bendPath = (path: string, source: Offset, target: Offset) => {
  const points = path.match(/-?[\d.]+(?:e-?\d+)?,-?[\d.]+(?:e-?\d+)?/g) ?? [];
  let i = 0;
  return path.replace(/(-?[\d.]+(?:e-?\d+)?),(-?[\d.]+(?:e-?\d+)?)/g, (_, x: string, y: string) => {
    const t = points.length > 1 ? i / (points.length - 1) : 0;
    i += 1;
    const dx = source.x + (target.x - source.x) * t;
    const dy = source.y + (target.y - source.y) * t;
    return `${Number(x) + dx},${Number(y) + dy}`;
  });
};

/**
 * The edges for the current node positions: an edge whose nodes were not dragged is the laid-out one (same object,
 * so it is not drawn again); the others get a bent path (`bendPath`) and a label moved by the mean of both offsets.
 */
const followNodes = (edges: Edge<ArcData>[], offsets: Map<string, Offset>) =>
  edges.map((e) => {
    const zero = { x: 0, y: 0 };
    const source = offsets.get(e.source) ?? zero;
    const target = offsets.get(e.target) ?? zero;
    if (!e.data || (source.x === 0 && source.y === 0 && target.x === 0 && target.y === 0)) return e;
    const label = e.data.labelPosition;
    return {
      ...e,
      data: {
        ...e.data,
        path: bendPath(e.data.path, source, target),
        labelPosition: label ? { x: label.x + (source.x + target.x) / 2, y: label.y + (source.y + target.y) / 2 } : null,
      },
    };
  });

/**
 * The download button at the top right of the graph: a menu with PDF, SVG, HTML and PNG and the option "With legend".
 * The file shows the whole graph as drawn (dragged nodes included), not just the part zoomed in on, redrawn as plain
 * shapes (`lib/dfgDrawing.ts`, `lib/dfgDownload.ts`). React Flow's panels (this button, the zoom controls) are not in it.
 *
 * @param drawing Returns the graph as currently drawn.
 * @param logName The log's name, for the file name.
 */
const DownloadMenu = ({ drawing, logName }: { drawing: () => Drawing; logName?: string }) => {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [legend, setLegend] = useState(true);
  const download = async (format: ImageFormat) => {
    setBusy(true);
    setError(null);
    try {
      await downloadDrawing(drawing(), format, logName, { legend });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel position="top-right">
      <Group gap={6} wrap="nowrap">
        {error && (
          <Text size="xs" c="red">
            {error}
          </Text>
        )}
        <Menu position="bottom-end" withinPortal shadow="sm" closeOnItemClick>
          <Menu.Target>
            <Tooltip label="Download the graph" withinPortal>
              <ActionIcon size="sm" variant="default" loading={busy} aria-label="Download the graph">
                <DownloadIcon size={13} />
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Download as</Menu.Label>
            {IMAGE_FORMATS.map(({ format, label, hint }) => (
              <Menu.Item key={format} onClick={() => download(format)}>
                <Text size="sm">{label}</Text>
                <Text size="xs" c="dimmed">{hint}</Text>
              </Menu.Item>
            ))}
            <Menu.Divider />
            <Box px="sm" py={6}>
              <Checkbox
                size="xs"
                label="With legend (object types and symbols)"
                checked={legend}
                onChange={(e) => setLegend(e.currentTarget.checked)}
              />
            </Box>
          </Menu.Dropdown>
        </Menu>
      </Group>
    </Panel>
  );
};

/** For `FitOnChange` without a kept view: fit every new layout. */
const NEVER = () => false;

/** Fit the view whenever a new layout arrives (not for a layout whose zoom and pan were restored, `skip`). */
const FitOnChange = ({ generation, skip }: { generation: number | null; skip: (generation: number | null) => boolean }) => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (generation !== null && !skip(generation)) requestAnimationFrame(() => fitView({ padding: 0.08, maxZoom: 1 }));
  }, [generation, fitView, skip]);
  return null;
};

/**
 * The directly-follows graph, laid out with ELK and drawn with React Flow (pan, zoom, fit).
 *
 * @param graph The graph from the backend.
 * @param colours Colour per object type.
 * @param direction Layout direction (left to right or top to bottom).
 * @param arcLabel What the arc labels show: traversals (`count`) or distinct objects.
 * @param compact Compact layout (little white space, `COMPACT_OPTIONS`).
 * @param height Height of the drawing area in pixels.
 * @param onDeselectActivity Called when the user double-clicks an activity node (to deselect it for all types).
 * @param exportColours Colour per object type in the downloads (light scheme; default: `colours`).
 * @param logName The log's name, for the file name of a download.
 * @param stateKey Where the layout, the dragged positions and zoom and pan are kept (e.g. `dfg.view.<log id>`), so that
 *   the graph looks as it was left when the page opens again with the same graph (`lib/keptView.ts`); none: not kept.
 */
export const DfgGraph = ({
  graph,
  colours,
  direction,
  arcLabel,
  compact,
  height,
  onDeselectActivity,
  exportColours,
  logName,
  stateKey,
}: {
  graph: DirectlyFollowsGraph;
  colours: Map<string, string>;
  direction: Direction;
  arcLabel: ArcLabel;
  compact: boolean;
  height: number;
  onDeselectActivity?: (activity: string) => void;
  exportColours?: Map<string, string>;
  logName?: string;
  stateKey?: string;
}) => {
  // The layout kept when the page was left, if it was made for the same graph and look settings.
  const inputs = [graph, direction, arcLabel, compact];
  const keptLayout = () => {
    const kept = stateKey ? recall<{ inputs: unknown[]; layout: Layout }>(`${stateKey}.layout`) : undefined;
    return kept && sameInputs(kept.inputs, inputs) ? kept.layout : null;
  };
  const [layout, setLayoutState] = useState<Layout | null>(keptLayout);
  const [error, setError] = useState<string | null>(null);
  const setLayout = (next: Layout) => {
    if (stateKey) keep(`${stateKey}.layout`, { inputs, layout: next });
    setLayoutState(next);
  };
  useEffect(() => {
    let cancelled = false;
    setError(null);
    const kept = keptLayout();
    if (kept) {
      setLayoutState(kept);
      return;
    }
    layoutGraph(graph, direction, arcLabel, compact).then(
      (result) => {
        if (cancelled) return;
        setLayout(result);
      },
      (err: unknown) => !cancelled && setError(String(err)),
    );
    return () => {
      cancelled = true;
    };
    // The kept layout and `setLayout` follow from these inputs and `stateKey`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, direction, arcLabel, compact]);
  const flow = useMemo(() => (layout ? toFlow(layout, colours) : null), [layout, colours]);
  // Dragged node positions, kept per layout generation: a new ELK run (a setting changed) starts from its own
  // positions.
  const generation = layout?.generation ?? null;
  type Dragged = { generation: number | null; nodes: Map<string, Node<NodeData>> };
  const [dragged, setDragged] = useState<Dragged>(() => {
    const kept = stateKey ? recall<Dragged>(`${stateKey}.dragged`) : undefined;
    return kept && kept.generation === generation ? kept : { generation: null, nodes: new Map() };
  });
  useEffect(() => {
    if (stateKey) keep(`${stateKey}.dragged`, dragged);
  }, [stateKey, dragged]);
  // Zoom and pan as left (only for the layout shown when the page opens again; new layouts are fitted).
  const { skipFit, ...viewport } = useKeptViewport(`${stateKey}.viewport`, generation);
  const nodes = useMemo(() => {
    const flowNodes = flow?.nodes ?? [];
    if (dragged.generation !== generation) return flowNodes;
    // Keep React Flow's state of a node (position, measured size), with the data of the current layout.
    return flowNodes.map((n) => {
      const kept = dragged.nodes.get(n.id);
      return kept ? { ...kept, data: n.data } : n;
    });
  }, [dragged, flow, generation]);
  const onNodesChange = useCallback(
    (changes: NodeChange<Node<NodeData>>[]) =>
      setDragged(() => ({ generation, nodes: new Map(applyNodeChanges(changes, nodes).map((n) => [n.id, n])) })),
    [generation, nodes],
  );
  // Right click on an activity copies its name (Nina, 2026-11-17); a note says so for a moment.
  const [copied, setCopied] = useState<string | null>(null);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(null), 1500);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const edges = useMemo(() => {
    if (!flow) return [];
    const laidOut = new Map(flow.nodes.map((n) => [n.id, n.position]));
    const offsets = new Map<string, Offset>();
    for (const n of nodes) {
      const p = laidOut.get(n.id);
      if (p && (p.x !== n.position.x || p.y !== n.position.y)) offsets.set(n.id, { x: n.position.x - p.x, y: n.position.y - p.y });
    }
    return followNodes(flow.edges, offsets);
  }, [flow, nodes]);
  // The graph as drawn (current positions, bent arcs), for the downloads, in the export colours (start and end arcs
  // grey, as on the page).
  const drawing = useMemo<Drawing>(() => {
    const light = exportColours ?? colours;
    return {
      nodes: nodes.map((n) => ({ x: n.position.x, y: n.position.y, data: n.data })),
      arcs: edges.flatMap((e) => (e.data ? [{ ...e.data, colour: arcColour(e.data, light) }] : [])),
      colours: light,
      arcLabel,
    };
  }, [nodes, edges, colours, exportColours, arcLabel]);
  const drawingRef = useRef(drawing);
  drawingRef.current = drawing;
  const currentDrawing = useCallback(() => drawingRef.current, []);

  if (error) return <Alert color="red">Layout failed: {error}</Alert>;
  if (!flow) return <Loader size="sm" />;
  if (flow.nodes.length === 0)
    return <Alert color="gray">Nothing to show: select an object type, or raise its variant or arc threshold.</Alert>;
  return (
    <Stack gap={4}>
      <Legend />
    <Box style={{ height, border: "1px solid var(--mantine-color-default-border)", borderRadius: 8, position: "relative" }}>
      {copied && (
        <Text
          size="xs"
          px={6}
          py={2}
          style={{ position: "absolute", top: 6, left: "50%", transform: "translateX(-50%)", zIndex: 10, borderRadius: 4, background: "var(--mantine-color-default-hover)" }}
        >
          Copied “{copied}”
        </Text>
      )}
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          nodesConnectable={false}
          nodesDraggable
          elementsSelectable={false}
          minZoom={0.05}
          maxZoom={3}
          {...(stateKey ? viewport : { fitView: true })}
          fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
          // Double click on an activity deselects it for every object type (Nina, 2026-11-19); no zoom on double click.
          zoomOnDoubleClick={false}
          onNodeDoubleClick={(event, node) => {
            event.preventDefault();
            const data = node.data as NodeData;
            if (data.kind === "activity") onDeselectActivity?.(data.activity);
          }}
          // Right click on an activity copies its name to the clipboard (Nina, 2026-11-17).
          onNodeContextMenu={(event, node) => {
            event.preventDefault();
            const data = node.data as NodeData;
            if (data.kind !== "activity") return;
            navigator.clipboard?.writeText(data.activity).then(
              () => setCopied(data.activity),
              () => setCopied(null),
            );
          }}
        >
          <Controls showInteractive={false} />
          <DownloadMenu drawing={currentDrawing} logName={logName} />
          <FitOnChange generation={generation} skip={stateKey ? skipFit : NEVER} />
        </ReactFlow>
      </ReactFlowProvider>
    </Box>
    </Stack>
  );
};
