import { MathEquation } from '../types';

export const INDEXED_MATH_EQUATIONS: MathEquation[] = [
  {
    id: 'eq_v3_sqrtprice_to_price',
    title: '1. Uniswap V3 / Algebra sqrtPriceX96 to Real Spot Price P Conversion',
    category: 'V3_VIRTUALIZATION',
    latexFormula: 'P = \\left( \\frac{\\text{sqrtPriceX96}}{2^{96}} \\right)^2',
    plainFormula: 'P = (sqrtPriceX96 / 2^96)^2',
    summary: 'Converts Uniswap V3 / Algebra Q64.96 binary fixed-point square root price into real spot price ratio between token1 and token0.',
    variableMap: [
      {
        symbol: 'sqrtPriceX96',
        name: 'V3 Q64.96 Square Root Price',
        routeSourceKey: 'pool.sqrtPriceX96',
        exampleVal: '192039201938201938201938201',
        unit: 'Fixed-Point 2^96 BigInt',
        description: 'Read directly from `slot0()` on the Uniswap V3 / Algebra Pool contract.',
      },
      {
        symbol: 'Q96',
        name: '2^96 Binary Shift Denominator',
        routeSourceKey: 'Constant BigInt',
        exampleVal: '79228162514264337593543950336',
        unit: 'Scalar Constant',
        description: 'Precision bit-shift scale used by Uniswap V3 core math library.',
      },
      {
        symbol: 'P',
        name: 'Spot Exchange Ratio (Price)',
        routeSourceKey: 'Derived Virtual Price',
        exampleVal: '3.1678',
        unit: 'Token1 / Token0',
        description: 'Instantaneous exchange rate between constituent tokens in the active tick.',
      },
    ],
    derivationSteps: [
      'Step 1: Divide 128-bit unsigned integer `sqrtPriceX96` by 2^96 using high-precision decimal math.',
      'Step 2: Square the resulting quotient: sqrtP * sqrtP = P.',
      'Step 3: Adjust for decimal differences between Token0 and Token1: P_adjusted = P * 10^(decimals0 - decimals1).',
    ],
  },
  {
    id: 'eq_v3_virtual_reserves',
    title: '2. Concentrated Liquidity L to CPMM Virtual Reserves (x_v = L / sqrtP; y_v = L * sqrtP)',
    category: 'V3_VIRTUALIZATION',
    latexFormula: 'x_v = \\frac{L}{\\sqrt{P}}, \\quad y_v = L \\cdot \\sqrt{P}',
    plainFormula: 'x_v = L / sqrt(P), y_v = L * sqrt(P)',
    summary: 'Linearizes tick-bounded UniV3 concentrated liquidity into equivalent global constant-product virtual reserves (x_v, y_v) where x_v = L / sqrt(P) and y_v = L * sqrt(P) for single-pass calculus optimization.',
    variableMap: [
      {
        symbol: 'L',
        name: 'Active Tick Liquidity',
        routeSourceKey: 'pool.liquidity',
        exampleVal: '912049201938492019',
        unit: 'Wei Liquidity Units',
        description: 'In-range liquidity value from `liquidity()` on the V3 / Algebra contract.',
      },
      {
        symbol: 'sqrt(P)',
        name: 'Square Root Price',
        routeSourceKey: 'sqrtPriceX96 / 2^96',
        exampleVal: '1.7798',
        unit: 'Dimensionless Ratio',
        description: 'Square root of spot price.',
      },
      {
        symbol: 'x_v',
        name: 'Virtual Token 0 Reserve (x_v = L / sqrtP)',
        routeSourceKey: 'Calculated Virtual rInUSD',
        exampleVal: '$3,420,000',
        unit: 'USD / Token 0 Amount',
        description: 'Virtual depth x_v of token0 acting as constant-product reserve.',
      },
      {
        symbol: 'y_v',
        name: 'Virtual Token 1 Reserve (y_v = L * sqrtP)',
        routeSourceKey: 'Calculated Virtual rOutUSD',
        exampleVal: '$1,850,000',
        unit: 'USD / Token 1 Amount',
        description: 'Virtual depth y_v of token1 acting as constant-product reserve.',
      },
    ],
    derivationSteps: [
      'Step 1: Fetch active liquidity L and slot0 sqrtPriceX96 from Polygon RPC.',
      'Step 2: Calculate sqrtP = sqrtPriceX96 / 2^96.',
      'Step 3: Compute x_v = L / sqrtP and y_v = L * sqrtP.',
      'Step 4: Verify virtual constant-product invariant k_virtual = x_v * y_v = L^2.',
    ],
  },
  {
    id: 'eq_cpmm_gross_output',
    title: '3. Constant Product Swap Output Function y(x) with Protocol Fees',
    category: 'CPMM_DERIVATIVE',
    latexFormula: 'y(x) = \\frac{y_v \\cdot x \\cdot (1 - \\gamma_{\\text{swap}})}{x_v + x \\cdot (1 - \\gamma_{\\text{swap}})}',
    plainFormula: 'y(x) = (y_v * x * (1 - f_swap)) / (x_v + x * (1 - f_swap))',
    summary: 'Exact output payout equation taking into account virtual reserves (x_v, y_v), protocol swap fees, and price impact slippage along the liquidity curve.',
    variableMap: [
      {
        symbol: 'x',
        name: 'Capital Injection Input',
        routeSourceKey: 'route.optimalInputUSD',
        exampleVal: '$28,500',
        unit: 'USD / Token Amount',
        description: 'Amount borrowed via flashloan and swapped into pool.',
      },
      {
        symbol: 'f_swap',
        name: 'DEX Protocol Swap Fee',
        routeSourceKey: 'pool.feeBps / 10000',
        exampleVal: '0.0005 (5 bps)',
        unit: 'Fraction',
        description: 'Fee percentage taken by liquidity providers (e.g. 0.05% or 0.30%).',
      },
      {
        symbol: 'x_v',
        name: 'Input Virtual Reserve (L / sqrtP)',
        routeSourceKey: 'pool.reserve0USD',
        exampleVal: '$3,420,000',
        unit: 'USD Value',
        description: 'Virtual swappable liquidity x_v on input side.',
      },
      {
        symbol: 'y_v',
        name: 'Output Virtual Reserve (L * sqrtP)',
        routeSourceKey: 'pool.reserve1USD',
        exampleVal: '$1,850,000',
        unit: 'USD Value',
        description: 'Virtual swappable liquidity y_v on output side.',
      },
    ],
    derivationSteps: [
      'Step 1: Compute effective input after fee: x_eff = x * (1 - f_swap).',
      'Step 2: Apply constant product invariant (x_v + x_eff) * (y_v - y) = x_v * y_v.',
      'Step 3: Solve for payout y(x): y(x) = (y_v * x_eff) / (x_v + x_eff).',
    ],
  },
  {
    id: 'eq_net_profit_objective',
    title: '4. Net Profit Objective Function P(x)',
    category: 'APEX_SOLVER',
    latexFormula: 'P(x) = y(x) - x \\cdot (1 + \\gamma_{\\text{flash}}) - G_{\\text{gas}}',
    plainFormula: 'P(x) = y(x) - x * (1 + f_flash) - GasFeeUSD',
    summary: 'Total net arbitrage yield accounting for multi-hop swap payout y(x), flashloan principal repayment, flashloan fee, and fixed gas cost.',
    variableMap: [
      {
        symbol: 'P(x)',
        name: 'Net Arbitrage Profit',
        routeSourceKey: 'route.netProfitUSD',
        exampleVal: '+$142.43',
        unit: 'USD Net Yield',
        description: 'Final net profit sent to executor contract wallet after tx execution.',
      },
      {
        symbol: 'y(x)',
        name: 'Gross Swap Payout Output',
        routeSourceKey: 'Calculated y(x*)',
        exampleVal: '$28,642.95',
        unit: 'USD Gross Return',
        description: 'Gross return generated by route swap path at input size x.',
      },
      {
        symbol: 'f_flash',
        name: 'Flashloan Vault Fee',
        routeSourceKey: 'Balancer V3 Vault = 0 bps',
        exampleVal: '0.0000 (0 bps)',
        unit: 'Fraction',
        description: 'Balancer V3 EIP-1153 transient storage flashloan has 0% fee on Polygon.',
      },
      {
        symbol: 'G_gas',
        name: 'Polygon Gas Transaction Cost',
        routeSourceKey: 'route.estimatedGasUSD',
        exampleVal: '$0.52',
        unit: 'USD Gas Cost',
        description: 'Computed as: GasUsed (120k) * GasPrice (38 Gwei) * POL_Price ($0.55).',
      },
    ],
    derivationSteps: [
      'Step 1: Calculate gross output y(x) from final swap in route chain.',
      'Step 2: Deduct total flashloan repayment requirement x * (1 + f_flash).',
      'Step 3: Subtract network gas fee G_gas.',
    ],
  },
  {
    id: 'eq_analytical_apex_solver',
    title: '5. Analytical Profit Apex Closed-Form Solution (x*)',
    category: 'APEX_SOLVER',
    latexFormula: 'x^* = \\frac{\\sqrt{ \\frac{x_v y_v (1 - \\gamma_{\\text{swap}})}{1 + \\gamma_{\\text{flash}}} } - x_v}{1 - \\gamma_{\\text{swap}}}',
    plainFormula: 'x* = ( sqrt( (x_v * y_v * (1 - f_swap)) / (1 + f_flash) ) - x_v ) / (1 - f_swap)',
    summary: 'Closed-form exact global max capital size x* obtained by setting first derivative dP/dx = 0.',
    variableMap: [
      {
        symbol: 'x*',
        name: 'Optimal Flashloan Capital Size',
        routeSourceKey: 'route.optimalInputUSD',
        exampleVal: '$28,500',
        unit: 'USD Flashloan Amount',
        description: 'Exact capital size that produces maximum dollar net profit apex.',
      },
      {
        symbol: 'd(Profit)/dx',
        name: 'First Order Derivative',
        routeSourceKey: 'Calculus Solver',
        exampleVal: '0.0000',
        unit: 'Marginal Return Rate',
        description: 'Set to 0 at optimal capital x* to solve for peak apex.',
      },
      {
        symbol: 'x_v',
        name: 'Input Virtual Reserve (L / sqrtP)',
        routeSourceKey: 'pool.reserve0USD',
        exampleVal: '$3,420,000',
        unit: 'USD Value',
        description: 'Input pool virtual liquidity.',
      },
      {
        symbol: 'y_v',
        name: 'Output Virtual Reserve (L * sqrtP)',
        routeSourceKey: 'pool.reserve1USD',
        exampleVal: '$1,850,000',
        unit: 'USD Value',
        description: 'Output pool virtual liquidity.',
      },
    ],
    derivationSteps: [
      'Step 1: Take derivative dP/dx of net profit P(x) with respect to x.',
      'Step 2: Set dP/dx = [ x_v * y_v * (1 - f_swap) ] / [ x_v + x*(1 - f_swap) ]^2 - (1 + f_flash) = 0.',
      'Step 3: Isolate term [ x_v + x*(1 - f_swap) ]^2 = [ x_v * y_v * (1 - f_swap) ] / (1 + f_flash).',
      'Step 4: Take square root of both sides and solve for x*.',
    ],
  },
  {
    id: 'eq_baseline_alpha_condition',
    title: '6. Derivative at Zero Alpha Condition (dP/dx | x=0)',
    category: 'APEX_SOLVER',
    latexFormula: '\\left. \\frac{dP}{dx} \\right|_{x=0} = \\frac{y_v}{x_v} (1 - \\gamma_{\\text{swap}}) - (1 + \\gamma_{\\text{flash}}) > 0',
    plainFormula: '(y_v / x_v) * (1 - f_swap) - (1 + f_flash) > 0',
    summary: 'Evaluates if a route is mathematically capable of positive profit before running full numerical optimization.',
    variableMap: [
      {
        symbol: 'dP/dx | x=0',
        name: 'Baseline Marginal Yield',
        routeSourceKey: 'apexResult.derivativeAtZero',
        exampleVal: '+0.0485',
        unit: 'Dimensionless Ratio',
        description: 'Must be strictly > 0 for arbitrage profit to exist.',
      },
      {
        symbol: 'y_v / x_v',
        name: 'Virtual Spot Price Ratio',
        routeSourceKey: 'pool.reserve1USD / pool.reserve0USD',
        exampleVal: '1.042',
        unit: 'Price Ratio',
        description: 'Ratio of virtual reserves across swap path.',
      },
    ],
    derivationSteps: [
      'Step 1: Evaluate derivative dP/dx at input size x = 0.',
      'Step 2: If result <= 0, price ratio is insufficient to cover protocol swap fees. Discard route immediately.',
    ],
  },
  {
    id: 'eq_vqc_state_amplitude',
    title: '7. Variational Quantum Circuit (VQC) Quantum State Vector',
    category: 'VQC_QUANTUM',
    latexFormula: '|\\psi(\\boldsymbol{\\theta})\\rangle = \\prod_{l=1}^L U_{\\text{entangle}} \\left( \\prod_{i=1}^N R_z(\\phi_{i,l}) R_y(\\theta_{i,l}) \\right) |0\\rangle^{\\otimes N}',
    plainFormula: '|psi(theta)> = Product_Layers( U_cz * Product_Qubits( Rz(phi) * Ry(theta) ) ) |0000>',
    summary: 'Parameterized 4-qubit quantum state encoding reserve ratios, path lengths, gas price density, and TVL bottlenecks.',
    variableMap: [
      {
        symbol: '|psi(theta)>',
        name: 'Quantum State Vector',
        routeSourceKey: 'VQC Simulator',
        exampleVal: '4-Qubit Amplitude Superposition',
        unit: 'Hilbert Space State',
        description: 'Quantum state manipulated by rotation and entanglement gates.',
      },
      {
        symbol: 'P(Win)',
        name: 'Measurement Probability',
        routeSourceKey: 'route.vqcWinProbability',
        exampleVal: '0.915 (91.5%)',
        unit: 'Probability [0, 1]',
        description: 'Probability of collapse to winning state |1111>.',
      },
      {
        symbol: 'Alpha Score',
        name: 'VQC Ranking Score',
        routeSourceKey: 'route.vqcAlphaScore',
        exampleVal: '0.942',
        unit: 'Normalized Score [0, 1]',
        description: 'Derived expectation value from quantum circuit measurement.',
      },
    ],
    derivationSteps: [
      'Step 1: Encode route feature matrix into rotation angles theta and phi.',
      'Step 2: Apply hardware-efficient ansatz across 3 entangling layers.',
      'Step 3: Measure Z-basis observable to calculate VQC Alpha Ranker score.',
    ],
  },

  // ── TRANSIENT ACCOUNTING EQUATIONS (EIP-1153 off-chain simulation) ──────

  {
    id: 'eq_transient_state_vector',
    title: '8. Canonical Transient State Vector z_j (EIP-1153 Accounting)',
    category: 'TRANSIENT_ACCOUNTING',
    latexFormula:
      '\\mathbf{z}_{j+1} = \\Phi_j\\!\\left(\\mathbf{z}_j,\\, \\mathbf{x}_j,\\, \\boldsymbol{\\theta}_j\\right)',
    plainFormula: 'z[j+1] = Phi_j( z[j], x[j], theta[j] )',
    summary:
      'Each route leg j transforms the 8-slot transient state vector ' +
      'z = [B, D, F, G, T, R, M, H] through the protocol-specific transition ' +
      'function Phi_j, binding inventory value, debt, fees, gas, tip, risk ' +
      'reserve, model reserve, and integrity hash.',
    variableMap: [
      { symbol: 'z_j', name: 'Transient State at Leg j', routeSourceKey: 'transientTrace.legs[j]', exampleVal: '[B=28500, D=28500, F=1.42, G=0.52, T=0.18, R=0.22, M=0.17, H=0x...]', unit: '8-slot vector', description: 'Full accounting state written to EIP-1153 transient storage slots.' },
      { symbol: 'B_j', name: 'Inventory Value', routeSourceKey: 'leg.amountOut', exampleVal: '$28,642', unit: 'USD', description: 'Running token balance held by executor after leg j.' },
      { symbol: 'D_j', name: 'Debt Obligation', routeSourceKey: 'transientTrace.debtWithFee', exampleVal: '$28,500', unit: 'USD', description: 'Flashloan principal + fee. Stays constant D₀ until SETTLE.' },
      { symbol: 'H_j', name: 'Integrity Hash', routeSourceKey: 'transientTrace.integrityHash', exampleVal: '0x3f2a...b8c1', unit: 'bytes32', description: 'TSTORE commitment over route path, pools, and amounts.' },
    ],
    derivationSteps: [
      'Step 1: Balancer Vault UNLOCK — TSTORE(DEBT_SLOT, D₀ = borrowedAmount × (1 + fee)).',
      'Step 2: For each leg j: execute Phi_j (swap or liquidation), update B_j and F_j.',
      'Step 3: TSTORE(INTEGRITY_SLOT, H_j = keccak(routeId | pools | amounts)).',
      'Step 4: Balancer Vault SETTLE — TLOAD(DEBT_SLOT), verify B_final ≥ D₀, TSTORE(DEBT_SLOT, 0).',
    ],
  },

  {
    id: 'eq_transient_token_ledger',
    title: '9. Token-Level Transient Ledger Update Rule L_j(a)',
    category: 'TRANSIENT_ACCOUNTING',
    latexFormula:
      'L_j(a) = L_{j-1}(a) + I_j(a) - O_j(a) - C_j(a)',
    plainFormula: 'L[j](a) = L[j-1](a) + inflow[j](a) - outflow[j](a) - cost[j](a)',
    summary:
      'Running transient balance of asset a after leg j. ' +
      'Starts at L₀(b) = Q_borrowed for the flash-borrowed token, 0 for all others. ' +
      'Each swap leg debits the input asset and credits the output asset.',
    variableMap: [
      { symbol: 'L_j(a)', name: 'Transient Balance of Asset a', routeSourceKey: 'Derived per leg', exampleVal: '$28,642', unit: 'USD', description: 'TLOAD / TSTORE per token address per leg.' },
      { symbol: 'I_j(a)', name: 'Asset Received at Leg j', routeSourceKey: 'leg.amountOut', exampleVal: '$28,642', unit: 'USD', description: 'Amount of asset a received during leg j.' },
      { symbol: 'O_j(a)', name: 'Asset Sent at Leg j', routeSourceKey: 'leg.amountIn', exampleVal: '$28,500', unit: 'USD', description: 'Amount of asset a transferred out during leg j.' },
      { symbol: 'C_j(a)', name: 'Asset Cost at Leg j', routeSourceKey: 'leg.feeUSD', exampleVal: '$1.43', unit: 'USD', description: 'Protocol fee + gas reserve denominated in asset a.' },
    ],
    derivationSteps: [
      'Step 1: At flash borrow: TSTORE(BALANCE_SLOT[borrowedToken], Q_borrowed).',
      'Step 2: On each swap leg: TSTORE(BALANCE_SLOT[tokenIn], L[j-1](tokenIn) - amountIn).',
      'Step 3: TSTORE(BALANCE_SLOT[tokenOut], L[j-1](tokenOut) + amountOut).',
      'Step 4: At SETTLE: TLOAD all balance slots and verify net is sufficient to repay D₀.',
    ],
  },

  {
    id: 'eq_transient_conservation',
    title: '10. Per-Leg Conservation Check (ε_j ≤ ε_allowed)',
    category: 'TRANSIENT_ACCOUNTING',
    latexFormula:
      '\\epsilon_j = \\left|V_j^{\\text{before}} - V_j^{\\text{after}} - C_j - \\Delta_j^{\\text{market}}\\right| \\leq \\varepsilon_{\\text{allowed}}',
    plainFormula: 'epsilon[j] = |valueBefore - valueAfter - cost - deltaMarket| <= epsilon_max',
    summary:
      "Mandatory per-leg conservation check. If any leg's residual |ε_j| exceeds " +
      'ε_allowed, the contract must revert with TRANSIENT_LEG_ACCOUNTING_MISMATCH. ' +
      'ε_allowed = $0.01 USD (configurable in chainConfig.ts).',
    variableMap: [
      { symbol: 'epsilon_j', name: 'Per-Leg Accounting Residual', routeSourceKey: 'leg.residualUSD', exampleVal: '$0.0000', unit: 'USD', description: 'Must be ≤ ε_allowed; otherwise revert.' },
      { symbol: 'C_j', name: 'Disclosed Leg Cost', routeSourceKey: 'leg.feeUSD + leg.gasReserveUSD + ...', exampleVal: '$2.05', unit: 'USD', description: 'Sum of protocol fee, gas, tip, risk, model reserves.' },
      { symbol: 'Delta_market', name: 'Price Impact / AMM Slippage', routeSourceKey: 'idealOut - actualOut', exampleVal: '$0.83', unit: 'USD', description: 'Value change from AMM curve execution (slippage).' },
      { symbol: 'epsilon_allowed', name: 'Max Allowed Residual', routeSourceKey: 'TRANSIENT_EPSILON_USD_MAX', exampleVal: '$0.01', unit: 'USD', description: 'Configurable threshold in src/config/chainConfig.ts.' },
    ],
    derivationSteps: [
      'Step 1: Before leg j, record V_before = TLOAD(INVENTORY_SLOT).',
      'Step 2: Execute leg (swap or liquidation), record V_after and all cost components.',
      'Step 3: Compute epsilon_j = |V_before - V_after - C_j - Delta_market|.',
      'Step 4: If epsilon_j > epsilon_allowed → REVERT("TRANSIENT_LEG_ACCOUNTING_MISMATCH").',
    ],
  },

  {
    id: 'eq_transient_debt_schedule',
    title: '11. Transient Debt Schedule — Balancer Vault Unlock/Settle (D₀)',
    category: 'TRANSIENT_ACCOUNTING',
    latexFormula:
      'D_0 = Q_{\\text{borrowed}} \\cdot (1 + \\gamma_{\\text{flash}})\\qquad ' +
      '\\text{SETTLE: } B_{\\text{final}} \\geq D_0',
    plainFormula: 'D0 = borrowedAmount * (1 + flashFeeRate);  assert finalInventory >= D0',
    summary:
      'The Balancer Vault (dual V2/V3 compatible) opens D₀ at UNLOCK and verifies ' +
      'repayment at SETTLE within the same flashloan callback. For the Balancer Vault ' +
      'on Polygon both compatibility modes charge 0% flash fee (γ_flash = 0), so ' +
      'D₀ = Q_borrowed exactly. C1/C2 routes repay with swap profit. ' +
      'LIQUIDATION routes repay with collateral bonus proceeds.',
    variableMap: [
      { symbol: 'D_0', name: 'Flashloan Debt Obligation', routeSourceKey: 'transientTrace.debtWithFee', exampleVal: '$28,500', unit: 'USD', description: 'TSTORE(DEBT_SLOT, D₀) at Balancer Vault UNLOCK.' },
      { symbol: 'gamma_flash', name: 'Balancer Vault Flash Fee Rate', routeSourceKey: 'BALANCER_VAULT_FLASH_FEE = 0', exampleVal: '0.0000 (0 bps)', unit: 'Fraction', description: 'Balancer Vault charges 0% on both V2 and V3 compat modes on Polygon.' },
      { symbol: 'B_final', name: 'Final Inventory After All Legs', routeSourceKey: 'Last leg amountOut', exampleVal: '$28,642', unit: 'USD', description: 'Must be ≥ D₀ for SETTLE to succeed. Excess = profit.' },
    ],
    derivationSteps: [
      'Step 1 (UNLOCK): Balancer Vault calls receiveFlashLoan() on executor. TSTORE(DEBT_SLOT, D₀).',
      'Step 2: Execute all swap / liquidation legs — inventory grows via arbitrage or liquidation bonus.',
      'Step 3 (SETTLE): At end of callback, TLOAD(DEBT_SLOT). Assert B_final ≥ D₀.',
      'Step 4: Transfer D₀ tokens back to Balancer Vault. TSTORE(DEBT_SLOT, 0). Profit = B_final - D₀.',
    ],
  },
];
