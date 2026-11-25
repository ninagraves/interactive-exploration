// What a page looked like when it was left: zoom and pan of a graph, scroll positions. Kept in memory per key
// (`lib/pageState.ts`, `keep`/`recall`), so that a page opened again looks as it was left, and only as long as it fits
// the current data. Documented in docs/hosting/state-and-caching.md, section "Page state".
import type { Viewport } from "@xyflow/react";
import { type RefObject, useCallback, useLayoutEffect, useRef, useState } from "react";
import { keep, recall } from "./pageState";

/** Zoom and pan of a React Flow graph, with the layout (`token`) they belong to. */
type KeptViewport = { token: unknown; viewport: Viewport };

/**
 * Zoom and pan of a React Flow graph, kept per key for the layout they were set on (`token`, e.g. the layout object
 * or its generation). Pass `defaultViewport` and `fitView` to `ReactFlow`, `onMoveEnd` too, and do not fit the view
 * for a token for which `skipFit` is true (it was restored as the user left it).
 *
 * @param key Where the view is kept, with the log id (e.g. `dfg.viewport.<log id>`).
 * @param token The current layout; read when the graph is first drawn.
 *
 * Example: `<ReactFlow {...view} />` with `const { skipFit, ...view } = useKeptViewport("dfg.viewport." + ocelId, layout)`.
 */
export const useKeptViewport = (key: string, token: unknown) => {
  // Only the view of the layout shown when the component mounts is restored; later layouts are fitted.
  const [restored] = useState(() => {
    const kept = recall<KeptViewport>(key);
    return kept && token !== null && token !== undefined && kept.token === token ? kept : null;
  });
  const current = useRef(token);
  current.current = token;
  const onMoveEnd = useCallback(
    (_event: unknown, viewport: Viewport) => keep(key, { token: current.current, viewport }),
    [key],
  );
  const skipFit = useCallback((t: unknown) => restored !== null && t === restored.token, [restored]);
  return { defaultViewport: restored?.viewport, fitView: restored === null, onMoveEnd, skipFit };
};

/** Longest time a scroll position is waited for (content that loads later makes the page tall enough). */
const SCROLL_RESTORE_MS = 4000;

/** The nearest ancestor of an element that scrolls vertically (Ocelescope's main area). */
const scrollParent = (element: HTMLElement | null): HTMLElement | null => {
  for (let e = element?.parentElement ?? null; e; e = e.parentElement) {
    const overflow = getComputedStyle(e).overflowY;
    if (overflow === "auto" || overflow === "scroll") return e;
  }
  return null;
};

const scrollStorageKey = (key: string) => `interactiveDfg.${key}`;

/**
 * Keeps the scroll position of a scrolling element per key (memory and the tab's sessionStorage) and restores it: the
 * position is set again on every animation frame until the content is tall enough (charts and lists load later), for
 * at most `SCROLL_RESTORE_MS`, and not any more once the user scrolls, clicks or types in it.
 *
 * @param box The scrolling element.
 * @param key Where the position is kept.
 * @returns The cleanup: keeps the current position and removes the listeners.
 */
const keepScrollOf = (box: HTMLElement, key: string) => {
  let target = recall<number>(key);
  if (target === undefined) {
    try {
      target = Number(sessionStorage.getItem(scrollStorageKey(key)) ?? 0) || 0;
    } catch {
      target = 0;
    }
  }
  let restoring = true;
  let frame = 0;
  const start = performance.now();
  const store = (top: number) => {
    keep(key, top);
    try {
      sessionStorage.setItem(scrollStorageKey(key), String(Math.round(top)));
    } catch {
      // Memory only.
    }
  };
  const stop = () => {
    restoring = false;
    cancelAnimationFrame(frame);
  };
  const restore = () => {
    box.scrollTop = target;
    if (Math.abs(box.scrollTop - target) < 2 || performance.now() - start > SCROLL_RESTORE_MS) restoring = false;
    else frame = requestAnimationFrame(restore);
  };
  const onScroll = () => {
    if (!restoring) keep(key, box.scrollTop);
  };
  const onPageHide = () => store(restoring ? target : box.scrollTop);
  const userEvents = ["wheel", "touchstart", "keydown", "mousedown"] as const;
  for (const e of userEvents) box.addEventListener(e, stop, { passive: true });
  box.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("pagehide", onPageHide);
  restore();
  return () => {
    store(restoring ? target : box.scrollTop);
    stop();
    for (const e of userEvents) box.removeEventListener(e, stop);
    box.removeEventListener("scroll", onScroll);
    window.removeEventListener("pagehide", onPageHide);
  };
};

/**
 * Keeps the scroll position of a page per key and restores it when the page opens again (`keepScrollOf`). The page
 * itself does not scroll but Ocelescope's main area around it does, so the ref goes on the page's outermost element
 * and the nearest scrolling ancestor is used.
 *
 * @param key Where the position is kept (e.g. `scroll.<log id>./interactiveDfg/dfg`).
 * @returns A ref for an element inside the scrolling area.
 */
export const useKeptScroll = <E extends HTMLElement>(key: string): RefObject<E | null> => {
  const anchor = useRef<E>(null);
  // A layout effect's cleanup runs before the page's elements are removed, so the position is still the user's.
  useLayoutEffect(() => {
    const box = scrollParent(anchor.current);
    return box ? keepScrollOf(box, key) : undefined;
  }, [key]);
  return anchor;
};

/**
 * Like `useKeptScroll`, for an element that scrolls itself (e.g. a list in a sidebar; for Mantine's `ScrollArea` pass
 * the ref as `viewportRef`).
 *
 * @param key Where the position is kept (e.g. `dfg.sidebar.activities.<log id>`).
 * @returns A ref for the scrolling element.
 */
export const useKeptScrollOf = <E extends HTMLElement>(key: string): RefObject<E | null> => {
  const box = useRef<E>(null);
  useLayoutEffect(() => (box.current ? keepScrollOf(box.current, key) : undefined), [key]);
  return box;
};
