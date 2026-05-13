import { SmartTapWorkspace } from "../features/smarttap/SmartTapWorkspace";
import { AppShell } from "./AppShell";

export function App() {
  return (
    <AppShell>
      <SmartTapWorkspace />
    </AppShell>
  );
}
