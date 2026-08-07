import 'dotenv/config';
import fs from 'node:fs/promises';
import path from 'node:path';
import type {
  MarketIntakeEnvelope,
} from '../src/engine/market/types';

const filePath = process.argv[2];

if (!filePath) {
  throw new Error(
    'Usage: tsx scripts/push-market-intake.ts <normalized-market-intake.json>',
  );
}

const apiBase = (
  process.env.APEX_MARKET_API_BASE ??
  'http://localhost:8797'
).replace(/\/+$/, '');

const intakeToken = process.env.MARKET_INTAKE_TOKEN?.trim();

const absolute = path.resolve(process.cwd(), filePath);
const raw = await fs.readFile(absolute, 'utf8');
const payload = JSON.parse(raw) as MarketIntakeEnvelope;

if (payload.schemaVersion !== 'apex.market.intake.v1') {
  throw new Error(
    `Invalid intake schema: ${String(payload.schemaVersion)}`,
  );
}

const response = await fetch(`${apiBase}/v1/intake`, {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    accept: 'application/json',
    ...(intakeToken
      ? { authorization: `Bearer ${intakeToken}` }
      : {}),
  },
  body: JSON.stringify(payload),
});

const body = await response.text();

if (!response.ok) {
  throw new Error(`Intake failed HTTP ${response.status}: ${body}`);
}

console.log(body);
