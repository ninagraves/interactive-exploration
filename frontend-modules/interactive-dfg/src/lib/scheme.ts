// The current colour scheme (light or dark), for the colours of the palette.
import { useComputedColorScheme } from "@mantine/core";
import type { Scheme } from "./palette";

/** The computed colour scheme of the page ("light" or "dark"). */
export const useScheme = () => useComputedColorScheme("light") as Scheme;
