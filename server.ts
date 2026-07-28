import express from 'express';
import path from 'path';
import { GoogleGenAI } from '@google/genai';
import { createServer as createViteServer } from 'vite';

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // Health Endpoint
  app.get('/api/health', (req, res) => {
    res.json({
      status: 'ok',
      engine: 'OMEGA-FINALLY-RICH-V5',
      chainId: 137,
      network: 'Polygon PoS',
      executor: '0xC1_ARB_EXECUTOR_ADDRESS',
      fundingVault: '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
      rustEngineStatus: 'OPTIMIZED_RELEASE_COMPILED',
      redisStream: 'omega:audit:simulations',
      timestamp: new Date().toISOString(),
    });
  });

  // Gemini Route Analysis Endpoint
  app.post('/api/gemini/analyze-route', async (req, res) => {
    try {
      const apiKey = process.env.GEMINI_API_KEY;
      if (!apiKey) {
        return res.status(500).json({ error: 'GEMINI_API_KEY environment variable is missing.' });
      }

      const { routeData, customPrompt } = req.body;

      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          },
        },
      });

      const systemInstruction = `You are OMEGA V5 Quantum MEV Analyst, an expert on Polygon PoS (Chain 137) DEX arbitrage, UniSwap V3 sqrtPriceX96 virtual reserve math, Aave V3 liquidations, Balancer V3 transient storage flashloans, VQC quantum surplus ranking, and low-latency Redis/SQL audit streams.
Provide high-density, action-oriented, technical analysis.
Output clear JSON structure containing:
- analysisSummary: concise string
- riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
- keyRiskFactors: array of strings
- executionOptimization: string
- suggestedSlippageBps: number
- sqlAuditQuery: string
- quantumAlphaScoreRecommendation: number`;

      const prompt = customPrompt
        ? `User Question: ${customPrompt}\nRoute Data: ${JSON.stringify(routeData)}`
        : `Analyze this Polygon PoS Arbitrage Route for maximum execution safety and profit optimization:
${JSON.stringify(routeData, null, 2)}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.6-flash',
        contents: prompt,
        config: {
          systemInstruction,
          responseMimeType: 'application/json',
          temperature: 0.2,
        },
      });

      const responseText = response.text || '{}';
      const parsedData = JSON.parse(responseText);

      res.json({
        success: true,
        data: parsedData,
      });
    } catch (error: any) {
      console.error('Error in Gemini analysis route:', error);
      res.status(500).json({
        success: false,
        error: error.message || 'Failed to generate route analysis via Gemini.',
      });
    }
  });

  // Vite middleware for development vs static production serving
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`OMEGA V5 Engine Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
