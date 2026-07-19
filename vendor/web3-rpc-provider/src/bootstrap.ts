import express, {Express, Request, Response} from 'express';
import puppeteer, {Browser} from 'puppeteer-core';
import { PickerClass } from "./common"
import { Garden } from './garden';
import * as pickers from './pickers';

function extraEndpoints(chainIds: number[]) {
  const raw = process.env.DODO_RPC_EXTRA_HTTP_URLS || process.env.RPC_ROTATION_HTTP_URLS || '';
  const urls = raw
    .split(',')
    .map((url) => url.trim())
    .filter((url) => /^https?:\/\//i.test(url) && !url.includes('${') && !url.includes('<') && !url.includes('>'));
  const uniqueUrls = Array.from(new Set(urls));
  return chainIds.flatMap((chainId) => uniqueUrls.map((url) => ({chainId, url})));
}

function uniqueEndpoints(values: {chainId: number; url: string}[]) {
  const seen = new Set<string>();
  const result = [];
  for (const value of values) {
    const key = `${value.chainId}:${value.url}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

async function bootstrap() {
  const port = Number(process.env.PORT || 3000);
  const app: Express = express();
  const browser: Browser = await puppeteer.launch({
      headless: true,
      executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
      args:
      ['--no-sandbox', '--disabled-setupid-sandbox'],
      // 更换成本地的 Chromium 地址
      // 浏览器访问 chrome://version/, 复制“可执行文件路径”
  });
  const map = new Map<string, PickerClass>();
  Object.entries(pickers).forEach(([key, value]) => {
    map.set(key, value);
    console.log(`Loaded ${key}.`);
  });
  const graden = new Garden(browser, map);

  app.get('/endpoints', async (req: Request<unknown, unknown, unknown,{ sources: string[], chains: number[] }>, res: Response) => {
    if (!req.query.sources || !req.query.chains) {
      res.send([]);
      return;
    }
    const chainIds = req.query.chains.map(Number);
    const result = await graden.collect(req.query.sources, chainIds)
    res.send(uniqueEndpoints([...result, ...extraEndpoints(chainIds)]));
  });

  app.get('/:chain/endpoints', async (req: Request<{ chain: string }, unknown, unknown,{ sources: string[] }>, res: Response) => {
    if (!req.query.sources || !req.params.chain) {
      res.send([]);
      return;
    }
    const chainIds = [Number(req.params.chain)];
    const result = await graden.collect(req.query.sources, chainIds)
    res.send(uniqueEndpoints([...result, ...extraEndpoints(chainIds)]));
  });

  app.listen(port, () => {
    console.log(`Listening on port ${port}`);
  });
}

void bootstrap();
