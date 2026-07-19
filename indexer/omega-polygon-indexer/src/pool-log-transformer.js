import "dotenv/config";
import { Kafka } from "kafkajs";

const kafkaBroker = process.env.KAFKA_BROKER || "127.0.0.1:9092";
const inputTopic = process.env.INDEXER_BLOCK_TOPIC || "omega.polygon.blocks.raw";
const outputTopic = process.env.INDEXER_POOL_LOG_TOPIC || "omega.polygon.pool.logs";
const groupId = process.env.INDEXER_TRANSFORMER_GROUP || "omega-pool-log-transformer";

const POOL_EVENT_SIGNATURES = new Set([
  "0x1c411e9a96e071241f4f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1", // V2 Sync(uint112,uint112)
  "0xd78ad95fa46c994b6551d0da85fc275fe613f624d5e4b78d83d78b2d3f33ef", // V2 Swap
  "0xc42079f94a6350d7e6235f291749249f928cc2ac818eb64c8e71fdd0eabe", // V3/Algebra Swap
  "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488d4b6a1fbdce178f77", // V3 Mint
  "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c", // V3 Burn
]);

function parseMessage(buffer) {
  const text = buffer.toString("utf8");
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function collectLogs(node, out = []) {
  if (!node || typeof node !== "object") return out;
  if (Array.isArray(node)) {
    for (const item of node) collectLogs(item, out);
    return out;
  }
  if (Array.isArray(node.logs)) collectLogs(node.logs, out);
  if (Array.isArray(node.receipts)) collectLogs(node.receipts, out);
  if (Array.isArray(node.transactions)) collectLogs(node.transactions, out);
  if (node.address && Array.isArray(node.topics) && node.topics.length > 0) {
    out.push(node);
  }
  return out;
}

function blockNumberOf(payload, log) {
  const raw = log.blockNumber ?? payload.blockNumber ?? payload.number ?? payload.block?.number;
  if (typeof raw === "number") return raw;
  if (typeof raw === "string" && raw.startsWith("0x")) return Number.parseInt(raw, 16);
  if (typeof raw === "string") return Number.parseInt(raw, 10);
  return 0;
}

const kafka = new Kafka({ clientId: "omega-polygon-indexer", brokers: [kafkaBroker] });
const consumer = kafka.consumer({ groupId });
const producer = kafka.producer();

await consumer.connect();
await producer.connect();
await consumer.subscribe({ topic: inputTopic, fromBeginning: false });

await consumer.run({
  eachMessage: async ({ message }) => {
    const payload = parseMessage(message.value || Buffer.from("{}"));
    if (!payload) return;
    const logs = collectLogs(payload).filter((log) => {
      const topic0 = String(log.topics?.[0] || "").toLowerCase();
      return POOL_EVENT_SIGNATURES.has(topic0);
    });
    if (logs.length === 0) return;
    await producer.send({
      topic: outputTopic,
      messages: logs.map((log) => ({
        key: String(log.address || "").toLowerCase(),
        value: JSON.stringify({
          blockNumber: blockNumberOf(payload, log),
          txHash: log.transactionHash || log.transaction_hash || "",
          logIndex: log.logIndex ?? log.log_index ?? 0,
          address: String(log.address || "").toLowerCase(),
          topics: log.topics || [],
          data: log.data || "0x",
        }),
      })),
    });
  },
});
