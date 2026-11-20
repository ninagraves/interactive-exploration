// Module definition: name, label and pages of the module.
import { defineModule, defineModuleRoute } from "@ocelescope/core";
import { WorkflowIcon } from "lucide-react";
import DirectlyFollowsGraph from "./routes/DirectlyFollowsGraph";
import Instances from "./routes/Instances";

const dfgRoute = defineModuleRoute({
  name: "dfg",
  label: "Interactive DFG",
  requiresOcel: true,
  component: DirectlyFollowsGraph,
});

const instancesRoute = defineModuleRoute({
  name: "instances",
  label: "Instances",
  requiresOcel: true,
  component: Instances,
});

export default defineModule({
  name: "interactiveDfg",
  label: "Interactive DFG",
  description: "Interactive object-centric directly-follows graph",
  authors: [{ name: "Nina Graves" }],
  icon: WorkflowIcon,
  routes: [dfgRoute, instancesRoute],
});
