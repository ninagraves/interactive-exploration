// The activity search of the directly-follows graph sidebar (`components/DfgSettings.tsx`): by activity name, and
// chips for object types: picked chips stack; the list holds the activities that every picked type is involved in,
// most such events first (`activitiesOf`). Documented in docs/pages/interactive-dfg.md, section "Activity search".
// Plain TypeScript without imports (structural types only), so that Node can run it in `tests/test_dfg_frontend.py`.

/** What the search needs of an activity of the list (a `DfgActivityOption` of the route). */
export type SearchableActivity = {
  activity: string;
  selected_events: number;
  log_events: number;
  object_types: { object_type: string; events: number }[];
};

/**
 * Shortest query (letters, after trimming) that offers object types by a part of their name; a shorter query only
 * offers a type whose full name it is (fewer letters are not selective enough).
 */
export const CHIP_QUERY_MIN_LENGTH = 4;

/**
 * True if an activity's name contains the search text (case-insensitive). An empty query matches every activity.
 *
 * @param option The activity.
 * @param query The search text.
 */
export const activityMatches = (option: SearchableActivity, query: string) =>
  option.activity.toLowerCase().includes(query.trim().toLowerCase());

/**
 * The object types whose name contains the query (case-insensitive), in the order given (the sidebar's order: most
 * objects first). Below `CHIP_QUERY_MIN_LENGTH` letters only a type whose full name is the query. E.g. in
 * ["coil", "slab", "operator", "box"]: "oper" gives ["operator"], "coi" nothing, "box" ["box"].
 *
 * @param types The object types.
 * @param query The search text.
 */
export const matchingObjectTypes = (types: string[], query: string) => {
  const q = query.trim().toLowerCase();
  if (q === "") return [];
  if (q.length < CHIP_QUERY_MIN_LENGTH) return types.filter((t) => t.toLowerCase() === q);
  return types.filter((t) => t.toLowerCase().includes(q));
};

/**
 * The activities with a positive count, most first; ties by events with an object of a selected type, then events in
 * the log (both descending), then name.
 *
 * @param options The activities (any order).
 * @param count The count of an activity (e.g. its events of a type).
 */
export const rankedBy = <T extends SearchableActivity>(options: T[], count: (option: T) => number): T[] =>
  options
    .filter((o) => count(o) > 0)
    .sort(
      (x, y) =>
        count(y) - count(x) ||
        y.selected_events - x.selected_events ||
        y.log_events - x.log_events ||
        (x.activity < y.activity ? -1 : x.activity > y.activity ? 1 : 0),
    );

/**
 * The events of an activity with at least one object of a type (the unfold's number, `DfgActivityTypeOption.events`);
 * 0 if the type is not involved.
 *
 * @param option The activity.
 * @param type The object type.
 */
export const typeEvents = (option: SearchableActivity, type: string) =>
  option.object_types.find((t) => t.object_type === type)?.events ?? 0;

/**
 * The count of an activity for picked object type chips: the smallest of the picked types' events (`typeEvents`). The
 * route has no number of events shared by two types, so the smallest one is used (at most that many events can have
 * both). 0 if one of the types is not involved; without picked types, the events with an object of a selected type.
 * E.g. coil + slab for roll in the running example: min(1, 1) = 1.
 *
 * @param option The activity.
 * @param types Picked object types.
 */
export const chipCount = (option: SearchableActivity, types: string[]) =>
  types.length > 0 ? Math.min(...types.map((t) => typeEvents(option, t))) : option.selected_events;

/**
 * The activities that every picked type is involved in (`chipCount` > 0), most first (ties as in `rankedBy`). Without
 * picked types: all activities as given. E.g. running example: coil: crane move (4), quality check (4), load truck (2),
 * unload truck (2), cut (1), label (1), roll (1); coil + slab: roll (1).
 *
 * @param options The activities (any order).
 * @param types Picked object types.
 */
export const activitiesOf = <T extends SearchableActivity>(options: T[], types: string[]): T[] =>
  types.length === 0 ? options : rankedBy(options, (o) => chipCount(o, types));
