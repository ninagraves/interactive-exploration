// The page "Instances": the object profile (one row per object; rows can be selected), then, for the selected
// objects, their object traces and their object graph, each with its own settings row. Every object is treated
// alike: any object can be selected, in the table or by a double click in the charts.
// Documented in docs/pages/instances.md.
import { Box, Button, Card, Group, Pill, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { getObjectProfile } from "../api/interactiveDfg";
import { ModulePage } from "../components/ModulePage";
import { DEFAULT_OBJECT_GRAPH, ObjectGraphChart, type ObjectGraphSettings } from "../components/ObjectGraphChart";
import { ObjectProfileTable } from "../components/ObjectProfileTable";
import { DEFAULT_OBJECT_TRACES, ObjectTracesChart, type ObjectTracesSettings } from "../components/ObjectTracesChart";
import { DEFAULT_OBJECT_TYPES } from "../lib/dfgView";
import { usePageState } from "../lib/pageState";
import { emphasisColourMap } from "../lib/palette";
import { useScheme } from "../lib/scheme";

/** Selected objects shown at most as pills (the rest as "+ n more"). */
const MAX_PILLS = 30;

/**
 * The selected objects as removable pills, with "Clear". It sticks to the top of the window once scrolled to, so that
 * the selection stays visible and editable next to the charts below.
 *
 * @param selected The selection.
 * @param onChange Called with the new selection.
 */
const SelectionBar = ({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) => (
  <Box
    style={{
      position: "sticky",
      top: "var(--app-shell-header-offset, 0px)",
      zIndex: 5,
      background: "var(--mantine-color-body)",
      borderBottom: "1px solid var(--mantine-color-default-border)",
      padding: "6px 0",
    }}
  >
    <Group gap={6}>
      <Text size="sm" fw={500}>Selected ({selected.length}):</Text>
      {selected.slice(0, MAX_PILLS).map((o) => (
        <Pill key={o} withRemoveButton onRemove={() => onChange(selected.filter((x) => x !== o))}>
          {o}
        </Pill>
      ))}
      {selected.length > MAX_PILLS && <Text size="xs" c="dimmed">+ {selected.length - MAX_PILLS} more</Text>}
      <Button size="compact-xs" variant="subtle" onClick={() => onChange([])}>
        Clear
      </Button>
    </Group>
  </Box>
);

/** A card with a title, an optional reset button, settings and content. */
const ChartCard = ({ title, onReset, children }: { title: string; onReset?: () => void; children: React.ReactNode }) => (
  <Card withBorder padding="md">
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={4}>{title}</Title>
        {onReset && (
          <Button size="compact-xs" variant="subtle" onClick={onReset}>
            Reset settings
          </Button>
        )}
      </Group>
      {children}
    </Stack>
  </Card>
);

/** The content of the page for one log. */
const InstancesContent = ({ ocelId }: { ocelId: string }) => {
  const scheme = useScheme();
  const [selected, setSelected] = usePageState<string[]>(`instances.selected.${ocelId}`, []);
  const [objectGraphStored, setObjectGraph] = usePageState<ObjectGraphSettings>(`instances.objectGraph.${ocelId}`, DEFAULT_OBJECT_GRAPH);
  const objectGraphSettings = useMemo(() => ({ ...DEFAULT_OBJECT_GRAPH, ...objectGraphStored }), [objectGraphStored]);
  // Raised by "Reset settings" so that the graph is laid out again (drops dragged positions, zoom and pan).
  const [objectGraphLayout, setObjectGraphLayout] = useState(0);
  const [tracesStored, setTraces] = usePageState<ObjectTracesSettings>(`instances.traces.${ocelId}`, DEFAULT_OBJECT_TRACES);
  const tracesSettings = useMemo(() => ({ ...DEFAULT_OBJECT_TRACES, ...tracesStored }), [tracesStored]);
  // Object types of the log (most objects first, ties by name) from the filter options of the profile: the same
  // colours as on the page "Interactive DFG" (signature colours for the top types, paler colours for the others).
  const { data: profile } = useQuery({
    queryKey: ["interactiveDfg", "instances", "profile", ocelId, { limit: 1 }],
    queryFn: ({ signal }) => getObjectProfile(ocelId, { limit: 1 }, undefined, undefined, signal),
  });
  const colours = useMemo(() => {
    const info = profile?.columns.find((c) => c.column === "object_type");
    const types = (info?.values ?? []).map(([t]) => t ?? "");
    return emphasisColourMap(types.slice(0, DEFAULT_OBJECT_TYPES), types.slice(DEFAULT_OBJECT_TYPES), scheme);
  }, [profile, scheme]);
  // Double-clicking an object in the traces or the object graph selects it, or unselects it if it is selected.
  const toggle = useCallback((o: string) => setSelected((s) => (s.includes(o) ? s.filter((x) => x !== o) : [...s, o])), [setSelected]);

  return (
    <Stack gap="md">
      <ChartCard title="Object profile">
        <Text size="xs" c="dimmed">
          One row per object of the log. Tick rows to show their traces and object graph below; the selection is kept
          when paging, searching and sorting. Click a row to unfold it.
        </Text>
        <ObjectProfileTable ocelId={ocelId} selected={selected} onSelected={setSelected} />
      </ChartCard>
      {selected.length === 0 ? (
        <Text size="sm" c="dimmed">Select one or more objects in the object profile to see their traces and object graph.</Text>
      ) : (
        <>
          <SelectionBar selected={selected} onChange={setSelected} />
          <ChartCard title="Object traces" onReset={() => setTraces(DEFAULT_OBJECT_TRACES)}>
            <ObjectTracesChart ocelId={ocelId} objects={selected} colours={colours} settings={tracesSettings} onChange={setTraces} onToggle={toggle} />
          </ChartCard>
          <ChartCard
            title="Object graph"
            onReset={() => {
              setObjectGraph(DEFAULT_OBJECT_GRAPH);
              setObjectGraphLayout((k) => k + 1);
            }}
          >
            <ObjectGraphChart
              layoutKey={objectGraphLayout}
              ocelId={ocelId}
              objects={selected}
              colours={colours}
              settings={objectGraphSettings}
              onChange={setObjectGraph}
              onToggle={toggle}
            />
          </ChartCard>
        </>
      )}
    </Stack>
  );
};

/** The page. */
export default function Instances() {
  return <ModulePage title="Instances">{({ ocelId }) => <InstancesContent ocelId={ocelId} />}</ModulePage>;
}
