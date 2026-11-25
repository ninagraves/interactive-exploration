// How long the answers of the module's requests are kept in the browser. Documented in
// docs/hosting/state-and-caching.md, section "Page state".
import { type Query, type QueryClient, useQueryClient } from "@tanstack/react-query";

/**
 * How long the answer of a module request is kept in the browser after no page shows it any more (React Query's
 * `gcTime`; its default is 5 minutes). A page opened again within this time shows the kept answer at once and checks
 * it in the background (React Query refetches on mount, as before), so it is never older than the log. Longer means
 * more memory in the tab.
 */
export const KEEP_ANSWERS_MS = 30 * 60 * 1000;

/** Key prefix of the module's hand-written queries (the generated ones start with the route's URL). */
export const QUERY_PREFIX = "interactiveDfg";

/**
 * True if a query key belongs to the module: hand-written `["interactiveDfg", ...]` or a generated URL key.
 *
 * Example: `isModuleQuery(["interactiveDfg", "dfg", "abc", {}])` and
 * `isModuleQuery(["/api/external/modules/interactiveDfg/v1/status"])` are true.
 */
export const isModuleQuery = (key: readonly unknown[]) =>
  key[0] === QUERY_PREFIX || String(key[0]).includes("/interactiveDfg/v1/");

const raised = new WeakSet<QueryClient>();

/** Raise the `gcTime` of a module query to `KEEP_ANSWERS_MS` (React Query keeps the longest `gcTime` it saw). */
const raise = (query: Query) => {
  if (isModuleQuery(query.queryKey) && (query.gcTime ?? 0) < KEEP_ANSWERS_MS)
    query.setOptions({ ...query.options, gcTime: KEEP_ANSWERS_MS });
};

/**
 * Keep the module's answers for `KEEP_ANSWERS_MS` in Ocelescope's query client (once per client; queries of other
 * modules are left alone). Called by every page of the module (`ModulePage`).
 */
export const useKeptAnswers = () => {
  const client = useQueryClient();
  if (raised.has(client)) return;
  raised.add(client);
  const cache = client.getQueryCache();
  for (const query of cache.getAll()) raise(query);
  cache.subscribe((event) => {
    if (event.type === "added") raise(event.query);
  });
};
