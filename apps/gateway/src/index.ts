import "dotenv/config";
import { loadConfig } from "./config/loadConfig.js";
import { createGateway } from "./gateway/createGateway.js";

async function main() {
  const config = await loadConfig();
  const gateway = await createGateway(config);
  await gateway.start();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
