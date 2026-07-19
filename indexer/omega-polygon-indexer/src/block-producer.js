import "dotenv/config";
import { BlockPollerProducer } from "@maticnetwork/chain-indexer-framework/block_producers/block_polling_producer";

const kafkaBroker = process.env.KAFKA_BROKER || "127.0.0.1:9092";
const mongoUrl = process.env.INDEXER_MONGO_URL || "mongodb://127.0.0.1:27017/omega_indexer";
const topic = process.env.INDEXER_BLOCK_TOPIC || "omega.polygon.blocks.raw";
const rpcWsEndpoints = [
  process.env.POLYGON_WSS_URL,
  process.env.PRIMARY_WSS_URL,
  process.env.DISCOVERY_RPC_WSS,
].filter(Boolean);

if (rpcWsEndpoints.length === 0) {
  throw new Error("No Polygon WSS endpoint configured for indexer block producer");
}

const startBlock = process.env.INDEXER_START_BLOCK || "latest";
const producer = new BlockPollerProducer({
  startBlock,
  rpcWsEndpoints,
  blockPollingTimeout: Number(process.env.INDEXER_BLOCK_POLL_MS || "1000"),
  topic,
  maxReOrgDepth: Number(process.env.INDEXER_MAX_REORG_DEPTH || "128"),
  maxRetries: Number(process.env.INDEXER_MAX_RETRIES || "10"),
  mongoUrl,
  "bootstrap.servers": kafkaBroker,
  "security.protocol": "plaintext",
  blockSubscriptionTimeout: Number(process.env.INDEXER_BLOCK_SUB_TIMEOUT_MS || "120000"),
});

producer.on("blockProducer.fatalError", (error) => {
  console.error(`omega indexer block producer fatal: ${error.message}`);
  process.exit(1);
});

producer.start().catch((error) => {
  console.error(error);
  process.exit(1);
});
