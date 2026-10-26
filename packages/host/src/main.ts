import { createAgentHttpServer } from "./http/agentHttpServer.js";
import { createHostServices } from "./services/hostServices.js";

const repoRoot = valueAfter("--repo-root") || process.cwd();
const services = await createHostServices(repoRoot);
const server = createAgentHttpServer(services);

server.listen(services.settings.host.port, services.settings.host.bindHost, () => {
  const displayHost = services.settings.host.bindHost === "0.0.0.0" ? "localhost" : services.settings.host.bindHost;
  console.log(`Kevin host listening on http://${displayHost}:${services.settings.host.port}`);
  console.log(`GUI: http://${displayHost}:${services.settings.host.port}/ui/`);
});

function valueAfter(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
}
