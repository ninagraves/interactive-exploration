// The frame of the module's page: title, backend versions, then the page's content for the current log.
import { Alert, Group, Stack, Text, Title } from "@mantine/core";
import { useCurrentOcel } from "@ocelescope/core";
import type { ReactNode } from "react";
import { useGetStatus } from "../api/interactiveDfg";
import { errorText } from "../lib/errors";

export { errorText };

/** What a page's content gets from the frame. */
export type PageContext = {
  ocelId: string;
};

/** Backend versions, as a small grey line (confirms the connection). */
const Versions = () => {
  const { data: status, error } = useGetStatus();
  if (error)
    return (
      <Text size="sm" c="red">
        Backend not reachable: {errorText(error)}
      </Text>
    );
  return status ? (
    <Text size="xs" c="dimmed">
      Backend module {status.module_version}, Ocelescope {status.ocelescope_version}
    </Text>
  ) : null;
};

/**
 * A page of the module: title and backend versions, then the page's content once a log is selected. The module needs
 * no configuration: it works on any OCEL.
 *
 * @param title The page title.
 * @param children The content, given the id of the current log.
 */
export const ModulePage = ({ title, children }: { title: string; children: (context: PageContext) => ReactNode }) => {
  const { id: ocelId } = useCurrentOcel();
  return (
    <Stack p="md" gap="lg">
      <Group justify="space-between" align="flex-end">
        <Title order={2}>{title}</Title>
        <Versions />
      </Group>
      {ocelId ? children({ ocelId }) : <Alert color="gray">Select an event log to start.</Alert>}
    </Stack>
  );
};
