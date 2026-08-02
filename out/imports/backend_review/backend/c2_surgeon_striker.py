"""
APEX_OMEGA C2 Surgeon Striker - Refined Triple Oracle
Quantum decision layer: MIRROR | REVERSE | DO NOTHING

Integrates with coefficient math for pure algebraic precision.
"""

import hashlib
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class StorePrice:
    """
    Price at a single 'store' (DEX pool)
    """
    store_id: str
    price_usd: float
    liquidity_usdc: float = 1_000_000.0


class MerklePriceTree:
    """
    Merkle tree of prices - cryptographic proof of spread existence
    """
    def __init__(self, stores: List[StorePrice]):
        self.leaves = sorted(stores, key=lambda s: s.price_usd)
        self.min_store = self.leaves[0]
        self.max_store = self.leaves[-1]
        self.tree = self._build_merkle_tree([self._hash_leaf(s) for s in self.leaves])
    
    def _hash_leaf(self, store: StorePrice) -> str:
        data = f"{store.store_id}:{store.price_usd}:{store.liquidity_usdc}".encode()
        return hashlib.sha256(data).hexdigest()
    
    def _build_merkle_tree(self, leaves: List[str]) -> List[str]:
        tree = leaves[:]
        while len(tree) > 1:
            if len(tree) % 2 == 1:
                tree.append(tree[-1])
            tree = [hashlib.sha256((tree[i] + tree[i+1]).encode()).hexdigest() 
                    for i in range(0, len(tree), 2)]
        return tree
    
    def get_proof(self) -> Dict:
        spread_pct = (self.max_store.price_usd - self.min_store.price_usd) / self.min_store.price_usd * 100
        return {
            "buy_store": self.min_store.store_id,
            "buy_price": self.min_store.price_usd,
            "sell_store": self.max_store.store_id,
            "sell_price": self.max_store.price_usd,
            "raw_spread_pct": round(spread_pct, 4),
            "merkle_root": self.tree[0]
        }


def calculate_hybrid_buffer(
    raw_spread: float,
    ml_predicted_slippage: float,
    amount_usdc: float,
    volatility_factor: float = 1.0
) -> Tuple[float, Dict]:
    """
    Hybrid buffer calculation combining:
    - ML slippage prediction (÷3 from our optimization)
    - Raw spread constraints
    - Volatility adjustment
    - Amount-based scaling
    
    Returns (buffer_decimal, breakdown_dict)
    """
    # Base slippage from ML (divided by 3 as per our optimization)
    ml_slippage = ml_predicted_slippage / 3.0
    
    # Scale by volatility
    vol_adjusted_slip = ml_slippage * volatility_factor
    
    # Add amount-based component (larger trades need more buffer)
    amount_factor = np.log10(max(amount_usdc, 1)) / 6.0  # Log scale, max at $1M
    amount_buffer = raw_spread * 0.10 * amount_factor
    
    # Combine components
    total_buffer = vol_adjusted_slip + amount_buffer
    
    # Clamp to reasonable range
    total_buffer = np.clip(total_buffer, 0.001, raw_spread * 0.90)
    
    breakdown = {
        'ml_slippage': ml_slippage,
        'vol_adjusted': vol_adjusted_slip,
        'amount_buffer': amount_buffer,
        'total_buffer': total_buffer
    }
    
    return total_buffer, breakdown


# ====================== REFINED C2 SURGEON STRIKER ======================
def c2_surgeon_striker_execute(
    stores: List[StorePrice], 
    amount_usdc: float, 
    hybrid_buffer_fn,
    current_volatility: float = 1.0,      # market vol multiplier (1.0 = neutral)
    capital_cost_bps: float = 8.5,        # opportunity cost of tying capital (annualized bps)
    execution_probability: float = 0.92   # base fill probability
) -> Dict:
    """
    Refined C2: Three options with dynamic scoring, risk-weighting, and quantum decision logic.
    
    THREE ORACLES:
    --------------
    1. MIRROR: Amplify the aggressor path (buy low, sell high)
    2. REVERSE: Counter-flow harvest (sell low, buy high - rebalancing alpha)
    3. DO NOTHING: Capital preservation (ghost mode)
    
    QUANTUM DECISION:
    ----------------
    Score = Net Yield × Fill Probability × Volatility Adjustment
    Selects highest risk-adjusted score
    """
    tree = MerklePriceTree(stores)
    proof = tree.get_proof()
    raw_spread_dec = proof["raw_spread_pct"] / 100.0
    time_horizon_hours = 0.5  # assume short arb window

    # Base hybrid buffer (surgeon-tight)
    base_buffer, buffer_breakdown = hybrid_buffer_fn(
        raw_spread=raw_spread_dec,
        ml_predicted_slippage=raw_spread_dec * 0.68,
        amount_usdc=amount_usdc,
        volatility_factor=current_volatility * 0.88
    )

    results = {}

    # === OPTION 1: MIRROR (amplify the aggressor path) ===
    mirror_buffer = base_buffer * 1.12
    mirror_gross = amount_usdc * raw_spread_dec
    mirror_slip_risk = base_buffer * 0.25
    mirror_net = mirror_gross - (amount_usdc * (mirror_buffer + mirror_slip_risk))
    mirror_score = mirror_net * execution_probability * (1 - current_volatility * 0.15)

    results["MIRROR"] = {
        "action": f"MIRROR → Double down on {proof['buy_store']}→{proof['sell_store']} path with echoed sizing",
        "gross_usd": round(mirror_gross, 2),
        "buffer_pct": round(mirror_buffer * 100, 4),
        "net_usd": round(mirror_net, 2),
        "score": round(mirror_score, 2),
        "risk_adjusted_bps": round(mirror_net / amount_usdc * 10000, 2)
    }

    # === OPTION 2: REVERSE (counter-flow harvest) ===
    reverse_buffer = base_buffer * 0.79
    reverse_gross = amount_usdc * raw_spread_dec * 0.97   # small decay on reverse leg
    reverse_slip_risk = base_buffer * 0.18
    reverse_net = reverse_gross - (amount_usdc * (reverse_buffer + reverse_slip_risk))
    reverse_score = reverse_net * (execution_probability * 0.94) * (1 + current_volatility * 0.08)  # slight vol premium

    results["REVERSE"] = {
        "action": f"REVERSE → Counter {proof['sell_store']}→{proof['buy_store']} flow, harvesting rebound alpha",
        "gross_usd": round(reverse_gross, 2),
        "buffer_pct": round(reverse_buffer * 100, 4),
        "net_usd": round(reverse_net, 2),
        "score": round(reverse_score, 2),
        "risk_adjusted_bps": round(reverse_net / amount_usdc * 10000, 2)
    }

    # === OPTION 3: DO NOTHING (capital preservation mode) ===
    opportunity_cost = amount_usdc * (capital_cost_bps / 10000) * (time_horizon_hours / 8760)
    do_nothing_score = -opportunity_cost * 1.2   # slight penalty for missed alpha

    results["DO_NOTHING"] = {
        "action": "DO NOTHING — Ghost mode. Preserve capital for higher-probability silence.",
        "gross_usd": 0.0,
        "buffer_pct": 0.0,
        "net_usd": 0.0,
        "score": round(do_nothing_score, 2),
        "risk_adjusted_bps": 0.0
    }

    # Quantum decision layer: select the highest risk-adjusted score
    best_option = max(results.keys(), key=lambda k: results[k]["score"])
    recommended = results[best_option]

    return {
        "strategy": "C2_SURGEON_STRIKER_REFINED",
        "c1_trigger": None,  # link to your C1 call if needed
        "three_options": results,
        "recommended_move": best_option,
        "recommended_net_usd": round(recommended["net_usd"], 2),
        "recommended_score": round(recommended["score"], 2),
        "merkle_proof": proof,
        "buffer_breakdown": buffer_breakdown,
        "decision_logic": f"Score = Net Yield × Fill Prob × Vol Adjustment | Best: {best_option}",
        "style": "Refined triple oracle — Mirror amplifies, Reverse reflects, Silence preserves. The ledger now chooses with quantum grace."
    }


# ====================== COEFFICIENT INTEGRATION ======================
def c2_with_coefficient(
    buy_price: float,
    sell_price: float,
    amount_usdc: float,
    dex_fee_bps: float = 30,
    flash_fee_bps: float = 9,
    gas_buffer_usd: float = 0.02,
    current_volatility: float = 1.0,
    execution_probability: float = 0.92
) -> Dict:
    """
    Integrate C2 Surgeon Striker with Coefficient Math
    
    Combines:
    - Pure algebraic coefficient calculation
    - Quantum decision layer (Mirror/Reverse/DoNothing)
    - Risk-adjusted scoring
    """
    from coefficient_profit_calculator import CoefficientProfitCalculator
    
    # Calculate coefficient
    calc = CoefficientProfitCalculator(
        dex_fee_bps=dex_fee_bps,
        flash_fee_bps=flash_fee_bps,
        gas_buffer_usd=gas_buffer_usd,
        min_profit_usd=5.0
    )
    
    coeff_result = calc.calculate_optimal_size(buy_price, sell_price)
    
    # Build stores from prices
    stores = [
        StorePrice("BuyPool", buy_price, amount_usdc),
        StorePrice("SellPool", sell_price, amount_usdc)
    ]
    
    # Run C2 Surgeon Striker
    c2_result = c2_surgeon_striker_execute(
        stores,
        amount_usdc,
        calculate_hybrid_buffer,
        current_volatility=current_volatility,
        execution_probability=execution_probability
    )
    
    # Merge results
    return {
        "coefficient": {
            "coeff": coeff_result.coeff,
            "optimal_token_units": coeff_result.optimal_token_units,
            "net_profit_usd": coeff_result.net_profit_usd,
            "roi_percent": coeff_result.roi_percent,
            "is_profitable": coeff_result.is_profitable
        },
        "c2_surgeon": c2_result,
        "decision": {
            "recommended_move": c2_result["recommended_move"],
            "coefficient_says": "EXECUTE" if coeff_result.is_profitable else "SKIP",
            "c2_says": c2_result["recommended_move"],
            "consensus": "EXECUTE" if (coeff_result.is_profitable and c2_result["recommended_move"] != "DO_NOTHING") else "SKIP"
        }
    }


if __name__ == "__main__":
    # ====================== LIVE REFINED EXECUTION (4-store spread) ======================
    stores_example = [
        StorePrice("StoreA", 1.05),
        StorePrice("StoreB", 1.00),
        StorePrice("StoreC", 1.02),
        StorePrice("StoreD", 1.02),
    ]

    print("="*80)
    print("SAINT DRIP REFINED C2 TRIPLE-OPTION ORCHESTRA")
    print("="*80)
    print()
    
    c2_result = c2_surgeon_striker_execute(
        stores_example, 
        500_000, 
        calculate_hybrid_buffer, 
        current_volatility=1.15, 
        execution_probability=0.89
    )

    print("THREE ORACLES:")
    print("-" * 80)
    for opt, data in c2_result["three_options"].items():
        print(f"{opt:12} → Net: ${data['net_usd']:>10,.2f} | Buffer: {data['buffer_pct']:>7}% | Score: {data['score']:>10,.2f}")

    print()
    print("MERKLE PROOF:")
    print(f"  Buy:  {c2_result['merkle_proof']['buy_store']} @ ${c2_result['merkle_proof']['buy_price']}")
    print(f"  Sell: {c2_result['merkle_proof']['sell_store']} @ ${c2_result['merkle_proof']['sell_price']}")
    print(f"  Raw Spread: {c2_result['merkle_proof']['raw_spread_pct']}%")
    print(f"  Merkle Root: {c2_result['merkle_proof']['merkle_root'][:16]}...")
    print()
    
    print("="*80)
    print(f"**RECOMMENDED MOVE:** {c2_result['recommended_move']}")
    print(f"  Net: ${c2_result['recommended_net_usd']:,.2f}")
    print(f"  Score: {c2_result['recommended_score']:,.2f}")
    print("="*80)
    print()
    print(c2_result["style"])
    print()
    
    # ====================== COEFFICIENT INTEGRATION TEST ======================
    print()
    print("="*80)
    print("COEFFICIENT + C2 SURGEON INTEGRATION")
    print("="*80)
    print()
    
    integrated = c2_with_coefficient(
        buy_price=1.00,
        sell_price=1.05,
        amount_usdc=500_000,
        current_volatility=1.15
    )
    
    print("COEFFICIENT ANALYSIS:")
    print(f"  coeff: ${integrated['coefficient']['coeff']:.6f} per token")
    print(f"  Optimal size: {integrated['coefficient']['optimal_token_units']:.2f} tokens")
    print(f"  Net profit: ${integrated['coefficient']['net_profit_usd']:.2f}")
    print(f"  ROI: {integrated['coefficient']['roi_percent']:.4f}%")
    print(f"  Profitable: {'✅ YES' if integrated['coefficient']['is_profitable'] else '❌ NO'}")
    print()
    
    print("C2 SURGEON DECISION:")
    print(f"  Recommended: {integrated['c2_surgeon']['recommended_move']}")
    print(f"  Net: ${integrated['c2_surgeon']['recommended_net_usd']:,.2f}")
    print()
    
    print("CONSENSUS DECISION:")
    print(f"  Coefficient: {integrated['decision']['coefficient_says']}")
    print(f"  C2 Surgeon: {integrated['decision']['c2_says']}")
    print(f"  **FINAL:** {integrated['decision']['consensus']}")
    print()
    print("The silence has spoken — execute with precision.")
