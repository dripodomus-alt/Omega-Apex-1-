"""
APEX_OMEGA Hawkes Process Liquidation Predictor
Self-Exciting Point Process for Liquidation Cascade Prediction

Predicts liquidation clusters based on:
- Recent liquidation events
- Cross-protocol correlation
- Volatility cascades
- Collateral overlap

Theory: Liquidations are self-exciting (one triggers others)
Model: Hawkes Process with exponential decay kernel
"""

import numpy as np
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class HawkesLiquidationPredictor:
    """
    Predicts liquidation cascades using Hawkes self-exciting point process.
    
    Intensity function:
        λ(t) = μ + Σ α * exp(-β * (t - t_i))
    
    Where:
        μ = base liquidation rate
        α = excitation parameter (how much each event increases future rate)
        β = decay parameter (how fast the excitement fades)
        t_i = times of past liquidations
    """
    
    def __init__(self):
        # Hawkes parameters (tuned for DeFi liquidations)
        self.base_rate = 0.05  # μ: base liquidations per hour
        self.excitation = 0.8  # α: each liquidation increases rate by 80%
        self.decay = 2.0  # β: excitement halves every 0.35 hours
        
        # Event history
        self.liquidation_history = []  # List of (timestamp, protocol, collateral, debt)
        self.max_history_hours = 48
        
        # Protocol correlation matrix
        # If Compound USDC crashes → High probability of Aave USDC crash
        self.protocol_correlation = {
            ('compound', 'aave'): 0.85,
            ('aave', 'compound'): 0.85,
            ('compound', 'maker'): 0.70,
            ('aave', 'maker'): 0.70,
        }
        
        # Collateral overlap factor
        # Users often use same collateral across protocols
        self.collateral_overlap = {
            'WETH': 0.90,  # 90% of WETH users overlap across protocols
            'WBTC': 0.85,
            'WMATIC': 0.80,
            'USDC': 0.75,
            'DAI': 0.75,
        }
    
    def record_liquidation(
        self,
        protocol: str,
        collateral_token: str,
        debt_token: str,
        amount_usd: float,
        timestamp: datetime = None
    ):
        """
        Record a liquidation event for cascade prediction.
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.liquidation_history.append({
            'timestamp': timestamp,
            'protocol': protocol.lower(),
            'collateral': collateral_token.upper(),
            'debt': debt_token.upper(),
            'amount_usd': amount_usd
        })
        
        # Trim old events
        cutoff = datetime.now() - timedelta(hours=self.max_history_hours)
        self.liquidation_history = [
            event for event in self.liquidation_history
            if event['timestamp'] > cutoff
        ]
    
    def calculate_intensity(self, current_time: datetime = None) -> float:
        """
        Calculate current liquidation intensity λ(t).
        
        Higher intensity = higher probability of liquidation cascade.
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Base rate
        intensity = self.base_rate
        
        # Add contribution from each past event
        for event in self.liquidation_history:
            time_since_event = (current_time - event['timestamp']).total_seconds() / 3600  # hours
            
            if time_since_event >= 0:
                # Exponential decay kernel
                contribution = self.excitation * np.exp(-self.decay * time_since_event)
                intensity += contribution
        
        return intensity
    
    def predict_cascade_targets(
        self,
        trigger_protocol: str,
        trigger_collateral: str,
        trigger_amount_usd: float,
        top_n: int = 10
    ) -> List[Dict]:
        """
        Predict which positions are most likely to be liquidated next.
        
        Returns priority-ranked targets based on:
        1. Protocol correlation
        2. Collateral overlap
        3. Current Hawkes intensity
        4. Position size similarity
        
        Returns:
            [
                {
                    'target_protocol': 'aave',
                    'target_collateral': 'WETH',
                    'cascade_probability': 0.85,
                    'urgency_score': 0.92,
                    'estimated_profit': 450.0
                },
                ...
            ]
        """
        # Current intensity (how "hot" the market is)
        current_intensity = self.calculate_intensity()
        
        # Candidate protocols
        candidate_protocols = ['aave', 'compound', 'maker']
        
        predictions = []
        
        for target_protocol in candidate_protocols:
            if target_protocol == trigger_protocol.lower():
                continue  # Skip same protocol
            
            # Protocol correlation
            correlation_key = (trigger_protocol.lower(), target_protocol)
            protocol_corr = self.protocol_correlation.get(correlation_key, 0.5)
            
            # Collateral overlap
            collateral_overlap = self.collateral_overlap.get(trigger_collateral.upper(), 0.6)
            
            # Cascade probability
            # P(cascade) = intensity * protocol_corr * collateral_overlap
            cascade_prob = min(current_intensity * protocol_corr * collateral_overlap, 0.99)
            
            # Urgency score (higher = more urgent to check)
            # Based on recency of similar events
            similar_events = [
                e for e in self.liquidation_history
                if e['protocol'] == target_protocol
                and e['collateral'] == trigger_collateral.upper()
            ]
            
            if similar_events:
                last_similar = max(e['timestamp'] for e in similar_events)
                hours_since = (datetime.now() - last_similar).total_seconds() / 3600
                urgency = np.exp(-0.5 * hours_since)  # Decay over ~2 hours
            else:
                urgency = 0.5  # Default urgency
            
            # Estimated profit (proportional to trigger amount)
            estimated_profit = trigger_amount_usd * 0.05 * cascade_prob  # 5% liquidation bonus
            
            predictions.append({
                'target_protocol': target_protocol,
                'target_collateral': trigger_collateral.upper(),
                'cascade_probability': cascade_prob,
                'urgency_score': urgency,
                'estimated_profit': estimated_profit,
                'current_intensity': current_intensity,
                'protocol_correlation': protocol_corr,
                'collateral_overlap': collateral_overlap
            })
        
        # Sort by cascade probability * urgency
        predictions.sort(
            key=lambda x: x['cascade_probability'] * x['urgency_score'],
            reverse=True
        )
        
        return predictions[:top_n]
    
    def get_market_heat_index(self) -> Dict:
        """
        Get current market "heat" for liquidations.
        
        Returns:
            {
                'intensity': 0.85,
                'heat_level': 'HIGH',
                'recent_events_24h': 15,
                'cascade_risk': 0.78
            }
        """
        intensity = self.calculate_intensity()
        
        # Count recent events
        cutoff_24h = datetime.now() - timedelta(hours=24)
        recent_events = len([
            e for e in self.liquidation_history
            if e['timestamp'] > cutoff_24h
        ])
        
        # Heat level categorization
        if intensity < 0.1:
            heat_level = 'COLD'
        elif intensity < 0.5:
            heat_level = 'WARM'
        elif intensity < 1.0:
            heat_level = 'HOT'
        else:
            heat_level = 'EXTREME'
        
        # Cascade risk (probability of 3+ liquidations in next hour)
        # Using Poisson distribution with Hawkes intensity
        expected_count = intensity
        cascade_risk = 1 - np.exp(-expected_count) * (1 + expected_count + expected_count**2/2)
        
        return {
            'intensity': intensity,
            'heat_level': heat_level,
            'recent_events_24h': recent_events,
            'cascade_risk': cascade_risk,
            'recommendation': self._get_recommendation(heat_level)
        }
    
    def _get_recommendation(self, heat_level: str) -> str:
        """Get trading recommendation based on market heat."""
        if heat_level == 'EXTREME':
            return "🔴 MAXIMUM ALERT: Monitor all protocols continuously. Cascade imminent."
        elif heat_level == 'HOT':
            return "🟠 HIGH ALERT: Increase scan frequency. Liquidation cluster likely."
        elif heat_level == 'WARM':
            return "🟡 ELEVATED: Normal monitoring. Isolated liquidations possible."
        else:
            return "🟢 NORMAL: Standard scan intervals. Low liquidation probability."


# Singleton
_hawkes_instance = None


def get_hawkes_predictor() -> HawkesLiquidationPredictor:
    """Get or create singleton Hawkes predictor instance."""
    global _hawkes_instance
    if _hawkes_instance is None:
        _hawkes_instance = HawkesLiquidationPredictor()
    return _hawkes_instance


if __name__ == "__main__":
    # Test the Hawkes predictor
    predictor = HawkesLiquidationPredictor()
    
    print("\n" + "="*70)
    print("APEX_OMEGA HAWKES LIQUIDATION CASCADE PREDICTOR")
    print("="*70)
    
    # Simulate liquidation cascade scenario
    print("\n📊 Scenario: Flash Crash Simulation")
    print("-" * 70)
    
    # Event 1: Compound WETH liquidation
    predictor.record_liquidation(
        protocol='compound',
        collateral_token='WETH',
        debt_token='USDC',
        amount_usd=10000,
        timestamp=datetime.now() - timedelta(minutes=5)
    )
    print("⚡ Event 1: Compound WETH liquidation ($10k) - 5 min ago")
    
    # Event 2: Another Compound liquidation
    predictor.record_liquidation(
        protocol='compound',
        collateral_token='WETH',
        debt_token='DAI',
        amount_usd=15000,
        timestamp=datetime.now() - timedelta(minutes=2)
    )
    print("⚡ Event 2: Compound WETH liquidation ($15k) - 2 min ago")
    
    # Event 3: Maker liquidation (cross-protocol)
    predictor.record_liquidation(
        protocol='maker',
        collateral_token='WETH',
        debt_token='DAI',
        amount_usd=20000,
        timestamp=datetime.now() - timedelta(minutes=1)
    )
    print("⚡ Event 3: Maker WETH liquidation ($20k) - 1 min ago")
    
    # Get market heat
    heat = predictor.get_market_heat_index()
    print(f"\n🌡️  Market Heat Index:")
    print(f"   Intensity: {heat['intensity']:.2f}")
    print(f"   Heat Level: {heat['heat_level']}")
    print(f"   Recent Events (24h): {heat['recent_events_24h']}")
    print(f"   Cascade Risk: {heat['cascade_risk']*100:.1f}%")
    print(f"   {heat['recommendation']}")
    
    # Predict cascade targets
    targets = predictor.predict_cascade_targets(
        trigger_protocol='compound',
        trigger_collateral='WETH',
        trigger_amount_usd=20000,
        top_n=5
    )
    
    print(f"\n🎯 Predicted Cascade Targets (Priority Ranked):")
    print("-" * 70)
    for i, target in enumerate(targets, 1):
        print(f"{i}. {target['target_protocol'].upper()} / {target['target_collateral']}")
        print(f"   Cascade Probability: {target['cascade_probability']*100:.1f}%")
        print(f"   Urgency Score: {target['urgency_score']*100:.1f}%")
        print(f"   Estimated Profit: ${target['estimated_profit']:.2f}")
        print(f"   Protocol Correlation: {target['protocol_correlation']*100:.0f}%")
        print()
    
    print("="*70)
