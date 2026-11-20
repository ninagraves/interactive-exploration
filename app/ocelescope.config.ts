import type { OcelescopeConfig } from "@ocelescope/core";
import management from "@ocelescope/management";
import interactiveDfgModule from "@instance/interactive-dfg";

// `pnpm run add:frontend` adds local frontend modules here.
export default {
	modules: [management, interactiveDfgModule],
} satisfies OcelescopeConfig;
