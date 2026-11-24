// The name of a log in the session, from Ocelescope's OCEL endpoint (the same request and cache key as Ocelescope's
// own `useGetOcel`, so it is usually answered from the cache).
import { useQuery } from "@tanstack/react-query";
import { customFetch } from "./fetcher";

/**
 * The name of the log in the session (e.g. "running_example"), or undefined while loading or if the request fails.
 *
 * @param ocelId The log.
 * @returns The name.
 */
export const useLogName = (ocelId: string) => {
  const url = `/api/external/modules/ocel/v1/${ocelId}`;
  const { data } = useQuery({
    queryKey: [url],
    queryFn: ({ signal }) => customFetch<{ name: string }>({ url, method: "GET", signal }),
    staleTime: 60_000,
  });
  return data?.name;
};
