// Object profile of the page "Instances": one row per object of the log, searchable, filterable per column (filter
// icon in the column header), sortable, paginated, with a checkbox per row to select objects for the charts below.
// The overview shows counts (easy to sort); clicking a row unfolds it with the names behind the counts. A header row
// names the column groups. The table as shown can be exported as CSV or saved to the session.
// Documented in docs/pages/instances.md, section "Object profile".
import { Anchor, Box, Button, Chip, Group, Loader, Pill, Popover, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue, useElementSize } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { DownloadIcon, SaveIcon, SearchIcon } from "lucide-react";
import { type DataTableColumn, type DataTableColumnGroup, DataTable, type DataTableSortStatus } from "mantine-datatable";
import { useMemo, useState } from "react";
import {
  type DetailEvent,
  exportObjectProfileCsv,
  getObjectDetails,
  getObjectProfile,
  type ProfileExportRequest,
  type ProfileFilter,
  type ProfileFilterColumn,
  type ProfilePage,
  type ProfileQuery,
  type ProfileQuerySortBy,
  type ProfileRow,
  saveObjectProfile,
} from "../api/interactiveDfg";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { filterText, ProfileColumnFilter, type ValueFormat } from "./ProfileColumnFilter";
import { ShortList } from "./ShortList";

/** Rows per page offered (default 25). */
const PAGE_SIZES = [10, 25, 50, 100];

/** Column groups that can be shown or hidden, in table order. */
const GROUPS = ["Lifecycle", "Activities", "Connectedness"] as const;
type Group = (typeof GROUPS)[number];

/** Table state kept per log. */
type TableState = {
  search: string;
  /** Active column filters by column. */
  filters: Partial<Record<ProfileFilterColumn, ProfileFilter>>;
  sort: { columnAccessor: ProfileQuerySortBy; direction: "asc" | "desc" };
  page: number;
  pageSize: number;
  groups: Group[];
};

const DEFAULT_TABLE: TableState = {
  search: "",
  filters: {},
  sort: { columnAccessor: "object", direction: "asc" },
  page: 1,
  pageSize: 25,
  groups: [...GROUPS],
};

/**
 * A duration in seconds as a short text with at most two units, e.g. "2 h", "1 d 3 h", "4 min 30 s"; "–" if missing,
 * "0" for zero.
 */
export const duration = (seconds: number | null | undefined) => {
  if (seconds === null || seconds === undefined) return "–";
  if (seconds === 0) return "0";
  const units: [string, number][] = [["d", 86400], ["h", 3600], ["min", 60], ["s", 1]];
  const parts: string[] = [];
  let rest = Math.round(seconds);
  for (const [unit, size] of units) {
    const n = Math.floor(rest / size);
    if (n > 0 && parts.length < 2) parts.push(`${n} ${unit}`);
    if (n > 0) rest -= n * size;
    if (parts.length === 2) break;
  }
  return parts.join(" ") || `${seconds.toFixed(1)} s`;
};

/** A timestamp as "YYYY-MM-DD HH:MM:SS". */
const stamp = (value: string | null | undefined) => (value ? value.replace("T", " ").slice(0, 19) : "–");

/** An event with its activity, e.g. "pack (e3)". */
const eventText = (activity?: string | null, event?: string | null) => (event ? `${activity ?? "?"} (${event})` : "–");

/** One column of the table: where it belongs, its title and hover text, how its values look. */
type ColumnSpec = {
  accessor: ProfileFilterColumn;
  title: string;
  group: Group | "Object";
  format: ValueFormat;
  info?: string;
  render?: (r: ProfileRow) => React.ReactNode;
};

const count = (accessor: ProfileFilterColumn, title: string, group: Group, info?: string): ColumnSpec => ({
  accessor,
  title,
  group,
  format: "count",
  info,
  render: (r) => num((r as unknown as Record<string, number>)[accessor]),
});

/** All columns, in table order: object, Lifecycle, Activities, Connectedness. */
const COLUMNS: ColumnSpec[] = [
  { accessor: "object", title: "Object", group: "Object", format: "text" },
  { accessor: "object_type", title: "Object type", group: "Object", format: "text" },
  count("n_events", "Events", "Lifecycle", "Events that involve the object."),
  count("n_timestamps", "Timestamps", "Lifecycle", "Distinct timestamps of the object's events: events at the same time count once."),
  { accessor: "first", title: "First", group: "Lifecycle", format: "time", info: "Timestamp of the object's first event.", render: (r) => stamp(r.first) },
  { accessor: "last", title: "Last", group: "Lifecycle", format: "time", info: "Timestamp of the object's last event.", render: (r) => stamp(r.last) },
  { accessor: "lifespan", title: "Lifespan", group: "Lifecycle", format: "duration", info: "Last minus first timestamp.", render: (r) => duration(r.lifespan) },
  {
    accessor: "first_activity",
    title: "First activity",
    group: "Activities",
    format: "text",
    info: "Activity of the first event of the object's trace (events ordered by time, then activity name, then event id).",
    render: (r) => r.first_activity ?? "–",
  },
  { accessor: "last_activity", title: "Last activity", group: "Activities", format: "text", info: "Activity of the last event of the object's trace.", render: (r) => r.last_activity ?? "–" },
  count("n_activities", "Activities", "Activities", "Distinct activities of the object's events."),
  count("n_shared_events", "Shared events", "Connectedness", "Events of the object that involve at least one other object."),
  count("n_linked", "Linked objects", "Connectedness", "Other objects that share at least one event with this one."),
];

/** The shown columns (groups switched on). */
const shownColumns = (groups: Group[]) => COLUMNS.filter((c) => c.group === "Object" || groups.includes(c.group));

/**
 * The column groups of the table (one header row naming the groups above the column titles).
 *
 * @param specs The shown columns.
 * @param page The current page (filter options).
 * @param filters Active filters.
 * @param setFilter Sets or removes the filter of a column.
 */
const columnGroups = (
  specs: ColumnSpec[],
  page: ProfilePage | undefined,
  filters: TableState["filters"],
  setFilter: (column: ProfileFilterColumn, filter: ProfileFilter | undefined) => void,
): DataTableColumnGroup<ProfileRow>[] => {
  const infos = new Map((page?.columns ?? []).map((i) => [i.column, i]));
  const column = (s: ColumnSpec): DataTableColumn<ProfileRow> => ({
    accessor: s.accessor,
    title: s.info ? (
      <Tooltip label={s.info} withinPortal multiline w={320}>
        <span style={{ textDecoration: "underline dotted" }}>{s.title}</span>
      </Tooltip>
    ) : (
      s.title
    ),
    sortable: true,
    noWrap: true,
    textAlign: s.format === "count" || s.format === "duration" ? "right" : "left",
    render: s.render,
    filter: ({ close }: { close: () => void }) => (
      <ProfileColumnFilter
        key={JSON.stringify(filters[s.accessor] ?? null)}
        column={s.accessor}
        info={infos.get(s.accessor)}
        format={s.format}
        value={filters[s.accessor]}
        onChange={(f) => setFilter(s.accessor, f)}
        close={close}
      />
    ),
    filtering: !!filters[s.accessor],
  });
  const order: (Group | "Object")[] = ["Object", ...GROUPS];
  return order
    .map((g) => ({ g, cols: specs.filter((s) => s.group === g) }))
    .filter(({ cols }) => cols.length)
    .map(({ g, cols }) => ({
      id: g,
      title: <Text size="xs" fw={700} c="dimmed">{g === "Object" ? "" : g}</Text>,
      columns: cols.map(column),
    }));
};

/** Starts a download of a text file. */
const download = (name: string, content: string, type: string) => {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
};

/** An event as "pack (e3) · 2026-01-01 03:00:00", "–" if missing. */
const eventLine = (e: DetailEvent | null | undefined) => (e ? `${eventText(e.activity, e.event)} · ${stamp(e.time)}` : "–");

/** Linked objects listed at most (the rest as "(+n)" with the list on hover). */
const MAX_LINKS = 20;
/** Shared events listed per linked object at most (the rest as "(+n)" with the list on hover). */
const MAX_EVENTS = 5;

/** A labelled line of the unfolded row. */
const Line = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <Group gap={6} wrap="nowrap" align="flex-start">
    <Text size="xs" c="dimmed" w={110} style={{ flexShrink: 0 }}>{label}</Text>
    <Box style={{ fontSize: "var(--mantine-font-size-xs)" }}>{children}</Box>
  </Group>
);

/**
 * An unfolded row: first and last event, the activities with their number of events, and the linked objects with the
 * events they share (a click on a linked object adds it to the selection).
 *
 * @param ocelId The log.
 * @param row The row.
 * @param onPick Called with an object clicked in the details.
 * @param width Visible width of the table: the panel stays in view when the table scrolls sideways.
 */
const ObjectDetailsPanel = ({ ocelId, row, onPick, width }: { ocelId: string; row: ProfileRow; onPick: (object: string) => void; width: number }) => {
  const object = row.object;
  const { data, error } = useQuery({
    queryKey: ["interactiveDfg", "instances", "details", ocelId, object],
    queryFn: ({ signal }) => getObjectDetails(ocelId, { object }, undefined, signal),
  });
  if (error) return <Text size="xs" c="red">{errorText(error)}</Text>;
  if (!data) return <Loader size="xs" m="xs" />;
  const shown = data.linked.slice(0, MAX_LINKS);
  const rest = data.linked.slice(MAX_LINKS).map((l) => `${l.object}: ${l.count}`);
  return (
    <SimpleGrid cols={width > 1100 ? 3 : width > 560 ? 2 : 1} spacing="md" px="md" py="xs" style={{ position: "sticky", left: 0, width: width || undefined }}>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Lifecycle</Text>
        <Line label="First event">{eventLine(data.first_event)}</Line>
        <Line label="Last event">{eventLine(data.last_event)}</Line>
      </Stack>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Activities ({data.activities.length})</Text>
        <Box style={{ fontSize: "var(--mantine-font-size-xs)" }}>
          {data.activities.length ? data.activities.map((a) => `${a.activity} ${a.count}`).join(", ") : "–"}
        </Box>
      </Stack>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Linked objects ({data.linked.length})</Text>
        {shown.length
          ? shown.map((l) => (
              <Box key={l.object} style={{ fontSize: "var(--mantine-font-size-xs)" }}>
                <Anchor size="xs" component="button" type="button" onClick={() => onPick(l.object)} title="add to the selection">{l.object}</Anchor>
                {` (${l.object_type ?? "?"}): ${l.count} (`}
                <ShortList items={l.events} limit={MAX_EVENTS} separator=", " />
                {")"}
              </Box>
            ))
          : <Text size="xs" c="dimmed">–</Text>}
        {rest.length > 0 && <Text size="xs"><ShortList items={rest} limit={0} /></Text>}
      </Stack>
    </SimpleGrid>
  );
};

/**
 * Export of the table as shown (folded): all objects matching search and filters, in the current order, with the
 * shown columns. As a CSV file, or saved to the session as an Ocelescope "OCEL Mapping" resource.
 */
const ExportButtons = ({ ocelId, request }: { ocelId: string; request: ProfileExportRequest }) => {
  const [name, setName] = useState("Object profile");
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const rows = (n: number) => `${num(n)} ${n === 1 ? "row" : "rows"}`;
  const run = async (task: () => Promise<string>) => {
    setBusy(true);
    try {
      setMessage({ text: await task() });
    } catch (e) {
      setMessage({ text: errorText(e), error: true });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack gap={4} align="flex-end">
      <Group gap="xs" align="flex-end">
        <Button
          size="xs"
          variant="default"
          leftSection={<DownloadIcon size={14} />}
          loading={busy}
          onClick={() =>
            run(async () => {
              const csv = await exportObjectProfileCsv(ocelId, request);
              download(csv.file_name, csv.content, "text/csv");
              return `Downloaded ${csv.file_name} (${rows(csv.rows)}).`;
            })
          }
        >
          CSV
        </Button>
        <Popover position="bottom-end" withArrow trapFocus opened={saving} onChange={setSaving}>
          <Popover.Target>
            <Button size="xs" variant="default" leftSection={<SaveIcon size={14} />} loading={busy} onClick={() => setSaving((o) => !o)}>
              Save to session
            </Button>
          </Popover.Target>
          <Popover.Dropdown>
            <Stack gap="xs" w={240}>
              <TextInput size="xs" label="Resource name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
              <Text size="xs" c="dimmed">Saved as an OCEL Mapping: the objects with the shown columns as their values.</Text>
              <Button
                size="xs"
                onClick={() =>
                  run(async () => {
                    setSaving(false);
                    const saved = await saveObjectProfile(ocelId, { ...request, name });
                    return `Saved “${saved.name}” to the session (${rows(saved.rows)}).`;
                  })
                }
              >
                Save
              </Button>
            </Stack>
          </Popover.Dropdown>
        </Popover>
      </Group>
      {message && (
        <Text size="xs" c={message.error ? "red" : "dimmed"}>
          {message.text}
        </Text>
      )}
    </Stack>
  );
};

/**
 * The object profile table.
 *
 * @param ocelId The log.
 * @param selected Ids of the selected objects (kept across pages and searches).
 * @param onSelected Called with the new selection.
 */
export const ObjectProfileTable = ({ ocelId, selected, onSelected }: { ocelId: string; selected: string[]; onSelected: (ids: string[]) => void }) => {
  const [stored, setStored] = usePageState<TableState>(`instances.table.v1.${ocelId}`, DEFAULT_TABLE);
  const state = { ...DEFAULT_TABLE, ...stored };
  const set = (change: Partial<TableState>) => setStored((s) => ({ ...DEFAULT_TABLE, ...s, ...change }));
  const setFilter = (column: ProfileFilterColumn, filter: ProfileFilter | undefined) =>
    setStored((s) => {
      const filters = { ...(s.filters ?? {}) };
      if (filter) filters[column] = filter;
      else delete filters[column];
      return { ...DEFAULT_TABLE, ...s, filters, page: 1 };
    });
  const [search] = useDebouncedValue(state.search, 250);
  const filters = Object.values(state.filters).filter((f): f is ProfileFilter => !!f);
  const query: ProfileQuery = {
    search,
    filters,
    sort_by: state.sort.columnAccessor,
    descending: state.sort.direction === "desc",
    offset: (state.page - 1) * state.pageSize,
    limit: state.pageSize,
  };
  const { data, error, isFetching } = useQuery({
    queryKey: ["interactiveDfg", "instances", "profile", ocelId, query],
    queryFn: ({ signal }) => getObjectProfile(ocelId, query, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  const specs = useMemo(() => shownColumns(state.groups), [state.groups]);
  const groups = columnGroups(specs, data, state.filters, setFilter);
  const exportRequest: ProfileExportRequest = { ...query, columns: specs.map((s) => s.accessor) };
  const formats = new Map(COLUMNS.map((c) => [c.accessor, c]));
  const { ref, width } = useElementSize();
  const selectedRecords = useMemo(() => selected.map((object) => ({ object }) as ProfileRow), [selected]);

  return (
    <Stack gap="xs" ref={ref}>
      <Group gap="md" align="flex-end" justify="space-between">
        <Group gap="md" align="flex-end">
          <TextInput
            size="xs"
            label="Search"
            placeholder="id, object type, first or last activity"
            leftSection={<SearchIcon size={14} />}
            value={state.search}
            onChange={(e) => set({ search: e.currentTarget.value, page: 1 })}
            w={300}
          />
          <div>
            <Text size="xs" fw={500}>Columns</Text>
            <Chip.Group multiple value={state.groups} onChange={(v) => set({ groups: GROUPS.filter((g) => v.includes(g)) })}>
              <Group gap={4}>
                {GROUPS.map((g) => (
                  <Chip key={g} value={g} size="xs" variant="outline">{g}</Chip>
                ))}
              </Group>
            </Chip.Group>
          </div>
        </Group>
        <ExportButtons ocelId={ocelId} request={exportRequest} />
      </Group>
      {data && (
        <Text size="sm">
          <b>{num(data.total)}</b>
          {data.total === data.objects ? ` object${data.total === 1 ? "" : "s"} listed` : ` of ${num(data.objects)} objects listed (search and filters)`}
        </Text>
      )}
      {filters.length > 0 && (
        <Group gap={6}>
          <Text size="xs" c="dimmed">Filters:</Text>
          {filters.map((f) => {
            const spec = formats.get(f.column);
            return (
              <Pill key={f.column} size="sm" withRemoveButton onRemove={() => setFilter(f.column, undefined)}>
                {`${spec?.title ?? f.column}: ${filterText(f, spec?.format ?? "text")}`}
              </Pill>
            );
          })}
          <Anchor size="xs" component="button" type="button" onClick={() => set({ filters: {}, page: 1 })}>
            Clear all
          </Anchor>
        </Group>
      )}
      {error ? (
        <Text size="sm" c="red">{errorText(error)}</Text>
      ) : (
        <DataTable<ProfileRow>
          withTableBorder
          withColumnBorders
          striped
          highlightOnHover
          fz="xs"
          minHeight={160}
          idAccessor="object"
          records={data?.rows ?? []}
          fetching={isFetching && !data}
          groups={groups}
          totalRecords={data?.total ?? 0}
          page={state.page}
          onPageChange={(page) => set({ page })}
          recordsPerPage={state.pageSize}
          recordsPerPageOptions={PAGE_SIZES}
          onRecordsPerPageChange={(pageSize) => set({ pageSize, page: 1 })}
          sortStatus={state.sort as DataTableSortStatus<ProfileRow>}
          onSortStatusChange={(s) => set({ sort: { columnAccessor: s.columnAccessor as ProfileQuerySortBy, direction: s.direction }, page: 1 })}
          rowExpansion={{
            allowMultiple: true,
            content: ({ record }) => (
              <ObjectDetailsPanel ocelId={ocelId} row={record} width={width - 2} onPick={(o) => onSelected(selected.includes(o) ? selected : [...selected, o])} />
            ),
          }}
          selectedRecords={selectedRecords}
          onSelectedRecordsChange={(records) => onSelected(records.map((r) => r.object))}
          noRecordsText="No object matches."
          paginationText={({ from, to, totalRecords }) => `${num(from)}–${num(to)} of ${num(totalRecords)} objects`}
        />
      )}
    </Stack>
  );
};
