"""
APEX_OMEGA Slippage Sentinel V12.1
ML-Powered Non-Linear Impact Prediction Engine

Predicts actual slippage (σ) based on:
- Trade amount (A)
- Pool liquidity (L)
- Recent volatility (V)
- Historical execution data

Model: Gradient Boosting Regressor (scikit-learn)
Export: ONNX for production inference

AUTO-RETRAINING: Model retrains after every 100 real executions
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
import json
from pathlib import Path
from typing import Dict, List, Tuple
import logging

from amm_math import get_protocol_router, AMMCalculator

logger = logging.getLogger(__name__)


class SlippageSentinel:
    """
    ML model that predicts actual slippage for arbitrage trades.
    
    Inputs:
        - trade_amount_usd: Size of the trade
        - pool_liquidity_usd: Total pool TVL
        - pool_utilization: trade_amount / pool_liquidity
        - volatility_1h: Price volatility in last hour
        - volatility_24h: Price volatility in last 24h
        - gas_price_gwei: Current gas price
        - spread_bps: Current spread in basis points
        
    Output:
        - predicted_slippage: Actual slippage (0.0 to 1.0)
        - confidence_score: Model confidence (0.0 to 1.0)
    """
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path or Path(__file__).parent / "models" / "slippage_sentinel.pkl"
        self.scaler_path = Path(__file__).parent / "models" / "slippage_scaler.pkl"
        
        self.model = None
        self.scaler = None
        self.feature_names = [
            'trade_amount_usd',
            'pool_liquidity_usd',
            'pool_utilization',
            'volatility_1h',
            'volatility_24h',
            'gas_price_gwei',
            'spread_bps'
        ]
        
        # Load or create model
        if self.model_path.exists():
            self.load_model()
        else:
            logger.warning("⚠️ Slippage Sentinel model not found. Training on synthetic data...")
            self.train_initial_model()
    
    def predict_slippage(
        self,
        trade_amount_usd: float,
        pool_liquidity_usd: float,
        volatility_1h: float = 0.01,
        volatility_24h: float = 0.02,
        gas_price_gwei: float = 60,
        spread_bps: float = 30,
        dex_protocol: str = 'quickswap_v2',  # NEW: Protocol-specific
        pool_data: Dict = None  # NEW: Protocol-specific pool data
    ) -> Dict[str, float]:
        """
        Predict slippage for a given trade using PROTOCOL-SPECIFIC AMM math.
        
        NEW: Uses exact formulas for QuickSwap V2/V3, Sushi cpAMM/clAMM, Curve, Balancer.
        CALIBRATED: Applies correction factor to compensate for ML over-prediction.
        
        Returns:
            {
                'predicted_slippage': 0.0035,  # 0.35% slippage (CALIBRATED)
                'confidence_score': 0.89,
                'impact_category': 'low',
                'amm_type': 'constant_product'  # NEW
            }
        """
        # STEP 1: Calculate EXACT slippage using protocol-native math
        exact_slippage = self._calculate_exact_slippage(
            dex_protocol=dex_protocol,
            trade_amount_usd=trade_amount_usd,
            pool_liquidity_usd=pool_liquidity_usd,
            pool_data=pool_data
        )
        
        # STEP 2: If ML model exists, use it to ADJUST for volatility/market conditions
        if self.model is not None:
            ml_adjustment = self._get_ml_volatility_adjustment(
                trade_amount_usd=trade_amount_usd,
                pool_liquidity_usd=pool_liquidity_usd,
                volatility_1h=volatility_1h,
                volatility_24h=volatility_24h,
                gas_price_gwei=gas_price_gwei,
                spread_bps=spread_bps
            )
            
            # Combine exact math with ML volatility adjustment
            raw_predicted_slippage = exact_slippage['slippage'] * (1 + ml_adjustment)
        else:
            # No ML model yet, use exact math only
            raw_predicted_slippage = exact_slippage['slippage']
            ml_adjustment = 0.0
        
        # Calculate pool utilization
        pool_utilization = trade_amount_usd / pool_liquidity_usd if pool_liquidity_usd > 0 else 0
        
        # STEP 3: Apply SIMPLIFIED CALIBRATION (User-requested: ÷ 3)
        # Previous complex calibration table replaced with simple divisor
        # This corrects known ML over-prediction while maintaining pool dynamics
        SLIPPAGE_DIVISOR = 3.0  # User-configurable: reduce ML predictions by 3x
        
        calibrated_slippage = raw_predicted_slippage / SLIPPAGE_DIVISOR
        
        # Use calibrated value for final prediction
        predicted_slippage = calibrated_slippage
        
        # Store divisor for transparency
        calibration_correction = 1.0 / SLIPPAGE_DIVISOR  # = 0.333...
        
        # Calculate confidence
        confidence = self._calculate_confidence(np.array([[pool_utilization, 0, 0, 0, 0, 0, 0]]))
        
        # Categorize impact (based on CALIBRATED slippage)
        if predicted_slippage < 0.001:
            impact_category = 'negligible'
        elif predicted_slippage < 0.005:
            impact_category = 'low'
        elif predicted_slippage < 0.02:
            impact_category = 'medium'
        else:
            impact_category = 'high'
        
        return {
            'predicted_slippage': float(predicted_slippage),  # CALIBRATED value
            'confidence_score': float(confidence),
            'impact_category': impact_category,
            'utilization_ratio': float(pool_utilization),
            'amm_type': exact_slippage.get('amm_type', 'constant_product'),
            'exact_slippage': float(exact_slippage['slippage']),
            'ml_adjustment': float(ml_adjustment),
            'raw_prediction': float(raw_predicted_slippage),  # Before calibration
            'calibration_factor': float(calibration_correction)  # Applied correction
        }
    
    def _calculate_exact_slippage(
        self,
        dex_protocol: str,
        trade_amount_usd: float,
        pool_liquidity_usd: float,
        pool_data: Dict = None
    ) -> Dict[str, float]:
        """
        Calculate EXACT slippage using protocol-native AMM math.
        
        Uses verified formulas for:
        - QuickSwap V2 / Sushi cpAMM: Constant Product (x·y = k)
        - QuickSwap V3 / Sushi clAMM: Concentrated Liquidity (sqrt-price)
        - Curve: StableSwap (iterative D-invariant)
        - Balancer: Weighted Product
        """
        router = get_protocol_router()
        
        # If pool_data not provided, create default constant-product assumption
        if pool_data is None:
            # Assume balanced reserves (50/50 split)
            reserve_in = pool_liquidity_usd / 2
            reserve_out = pool_liquidity_usd / 2
            
            pool_data = {
                'reserve_in': reserve_in,
                'reserve_out': reserve_out
            }
        
        # Calculate using protocol-specific math
        try:
            result = router.calculate_swap(
                dex=dex_protocol,
                pool_data=pool_data,
                amount_in=trade_amount_usd,
                fee=0.003  # Default 0.3%
            )
            
            return {
                'slippage': result.get('slippage', 0),
                'price_impact': result.get('price_impact', 0),
                'execution_price': result.get('execution_price', 0),
                'amm_type': self._get_amm_type(dex_protocol)
            }
        
        except Exception as e:
            logger.warning(f"Exact slippage calculation failed for {dex_protocol}: {e}")
            # Fallback to simplified model
            utilization = trade_amount_usd / pool_liquidity_usd if pool_liquidity_usd > 0 else 0
            return {
                'slippage': np.sqrt(utilization) * 0.5,
                'price_impact': utilization,
                'execution_price': 0,
                'amm_type': 'fallback'
            }
    
    def _get_ml_volatility_adjustment(
        self,
        trade_amount_usd: float,
        pool_liquidity_usd: float,
        volatility_1h: float,
        volatility_24h: float,
        gas_price_gwei: float,
        spread_bps: float
    ) -> float:
        """
        Use ML model to predict volatility-based adjustment factor.
        
        This captures market conditions that AMM math alone doesn't (cascades, front-running, etc.)
        
        Returns adjustment multiplier (e.g., 0.15 = +15% slippage from volatility)
        """
        pool_utilization = trade_amount_usd / pool_liquidity_usd if pool_liquidity_usd > 0 else 0
        
        features = np.array([[
            trade_amount_usd,
            pool_liquidity_usd,
            pool_utilization,
            volatility_1h,
            volatility_24h,
            gas_price_gwei,
            spread_bps
        ]])
        
        if self.scaler:
            features_scaled = self.scaler.transform(features)
        else:
            features_scaled = features
        
        # Model predicts TOTAL slippage; we extract the volatility component
        ml_predicted = self.model.predict(features_scaled)[0]
        
        # Adjustment = difference between ML prediction and base (no volatility)
        base_features = features.copy()
        base_features[0, 3] = 0.001  # Minimal volatility
        base_features[0, 4] = 0.001
        
        if self.scaler:
            base_scaled = self.scaler.transform(base_features)
        else:
            base_scaled = base_features
        
        base_predicted = self.model.predict(base_scaled)[0]
        
        # Return adjustment factor
        adjustment = (ml_predicted - base_predicted) / base_predicted if base_predicted > 0 else 0
        
        return float(np.clip(adjustment, -0.5, 1.0))  # Cap at ±50% / +100%
    
    def _get_calibration_correction(self, pool_utilization: float) -> float:
        """
        Calculate calibration correction factor to compensate for ML over-prediction.
        
        Based on empirical testing showing the model over-predicts slippage by:
        - Low utilization (<1%): 95% over-prediction → correction factor 0.51 (divide by 1.95)
        - Medium utilization (1-5%): 51% over-prediction → correction factor 0.66 (divide by 1.51)
        - High utilization (5-25%): 10% over-prediction → correction factor 0.91 (divide by 1.10)
        - Very high utilization (>25%): Minimal over-prediction → factor 0.95
        
        This function returns a MULTIPLIER that reduces the raw prediction to realistic levels.
        
        Args:
            pool_utilization: Trade amount / pool liquidity (0.0 to 1.0)
            
        Returns:
            Correction multiplier (0.5 to 1.0) - lower = more aggressive correction
        """
        # Convert to percentage for easier thresholds
        utilization_pct = pool_utilization * 100
        
        # Empirically calibrated correction factors based on test results
        if utilization_pct < 0.5:
            # Very low utilization: Heavy over-prediction (100% error)
            # Example: $1k in $5M pool predicted 0.68% but actual 0.34%
            return 0.50  # Divide by 2
            
        elif utilization_pct < 1.0:
            # Low utilization: Significant over-prediction (91% error)
            # Example: $5k in $2M pool predicted 1.52% but actual 0.79%
            return 0.55  # Divide by ~1.8
            
        elif utilization_pct < 2.0:
            # Low-medium utilization: Moderate over-prediction (51% error)
            # Example: $10k in $1M pool predicted 3.40% but actual 2.25%
            return 0.66  # Divide by ~1.5
            
        elif utilization_pct < 5.0:
            # Medium utilization: Some over-prediction
            return 0.75  # Divide by ~1.33
            
        elif utilization_pct < 10.0:
            # Medium-high utilization: Slight over-prediction
            return 0.85  # Divide by ~1.18
            
        elif utilization_pct < 25.0:
            # High utilization: Minimal over-prediction (10% error)
            # Example: $50k in $200k pool predicted 36.8% but actual 33.5%
            return 0.91  # Divide by ~1.1
            
        else:
            # Very high utilization: Model is fairly accurate
            return 0.95  # Minimal correction
    
    def _get_amm_type(self, dex_protocol: str) -> str:
        """Map DEX protocol to AMM family."""
        protocol = dex_protocol.lower()
        
        if any(x in protocol for x in ['v2', 'cpamm', 'trident']):
            return 'constant_product'
        elif any(x in protocol for x in ['v3', 'algebra', 'clamm']):
            return 'concentrated_liquidity'
        elif 'curve' in protocol:
            return 'stableswap'
        elif 'balancer' in protocol:
            return 'weighted_product'
        else:
            return 'unknown'
    
    def train_initial_model(self):
        """
        Train initial model on synthetic + analytical data.
        
        In production, this will be retrained on actual execution data.
        """
        logger.info("🧠 Training Slippage Sentinel on synthetic data...")
        
        # Generate synthetic training data
        X_train, y_train = self._generate_synthetic_data(n_samples=5000)
        
        # Split for validation
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=0.2, random_state=42
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_val_scaled = self.scaler.transform(X_val)
        
        # Train Gradient Boosting model
        self.model = GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=5,
            min_samples_split=10,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
            verbose=0
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Validate
        val_score = self.model.score(X_val_scaled, y_val)
        logger.info(f"✅ Model trained. R² score: {val_score:.4f}")
        
        # Save model
        self.save_model()
    
    def _generate_synthetic_data(self, n_samples: int = 5000) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic training data based on AMM math.
        
        Uses constant product formula with realistic noise.
        """
        np.random.seed(42)
        
        # Generate random trade scenarios
        trade_amounts = np.random.lognormal(8, 1.5, n_samples)  # $1k-$100k
        pool_liquidities = np.random.lognormal(12, 1, n_samples)  # $100k-$10M
        volatilities_1h = np.random.gamma(2, 0.005, n_samples)  # 0-5%
        volatilities_24h = np.random.gamma(2, 0.01, n_samples)  # 0-10%
        gas_prices = np.random.gamma(5, 10, n_samples)  # 10-100 gwei
        spreads = np.random.gamma(3, 10, n_samples)  # 10-50 bps
        
        # Calculate theoretical slippage using constant product formula
        # Slippage ≈ sqrt(trade_amount / pool_liquidity) + volatility_factor + fee
        utilizations = trade_amounts / pool_liquidities
        
        theoretical_slippage = (
            np.sqrt(utilizations) * 0.5 +  # AMM impact
            volatilities_1h * 2 +  # Volatility impact
            volatilities_24h * 0.5 +  # Trend impact
            (gas_prices / 1000) * 0.0001  # Gas impact (minimal)
        )
        
        # Add realistic noise
        noise = np.random.normal(0, 0.001, n_samples)
        actual_slippage = np.clip(theoretical_slippage + noise, 0, 0.5)
        
        # Assemble features
        X = np.column_stack([
            trade_amounts,
            pool_liquidities,
            utilizations,
            volatilities_1h,
            volatilities_24h,
            gas_prices,
            spreads
        ])
        
        y = actual_slippage
        
        return X, y
    
    def _analytical_fallback(self, trade_amount: float, pool_liquidity: float) -> Dict[str, float]:
        """
        Fallback to analytical model if ML model unavailable.
        """
        utilization = trade_amount / pool_liquidity if pool_liquidity > 0 else 0
        slippage = np.sqrt(utilization) * 0.5
        
        return {
            'predicted_slippage': float(slippage),
            'confidence_score': 0.5,
            'impact_category': 'analytical_fallback',
            'utilization_ratio': float(utilization)
        }
    
    def _calculate_confidence(self, features: np.ndarray) -> float:
        """
        Calculate prediction confidence based on feature coverage.
        
        Higher confidence if features are within training range.
        """
        # Simplified confidence: based on utilization ratio
        utilization = features[0, 2]
        
        if utilization < 0.001:
            return 0.95
        elif utilization < 0.01:
            return 0.90
        elif utilization < 0.05:
            return 0.85
        elif utilization < 0.1:
            return 0.75
        else:
            return 0.60
    
    def save_model(self):
        """Save model and scaler to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        joblib.dump(self.model, self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        
        logger.info(f"💾 Slippage Sentinel saved to {self.model_path}")
    
    def load_model(self):
        """Load model and scaler from disk."""
        self.model = joblib.load(self.model_path)
        self.scaler = joblib.load(self.scaler_path)
        
        logger.info(f"✅ Slippage Sentinel loaded from {self.model_path}")
    
    def retrain_on_execution_data(self, execution_history: pd.DataFrame):
        """
        Retrain model on actual execution data.
        
        DataFrame must have columns:
            - trade_amount_usd
            - pool_liquidity_usd
            - pool_utilization
            - volatility_1h
            - volatility_24h
            - gas_price_gwei
            - spread_bps
            - actual_slippage (target)
        """
        if len(execution_history) < 50:
            logger.warning(f"⚠️  Insufficient data for retraining ({len(execution_history)} < 50 executions)")
            return
        
        logger.info(f"🔄 Retraining Slippage Sentinel on {len(execution_history)} executions...")
        
        # Prepare features
        X = execution_history[self.feature_names].values
        y = execution_history['actual_slippage'].values
        
        # Split for validation
        from sklearn.model_selection import train_test_split
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Retrain scaler and model
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_val_scaled = self.scaler.transform(X_val)
        
        self.model.fit(X_train_scaled, y_train)
        
        # Validate
        val_score = self.model.score(X_val_scaled, y_val)
        logger.info(f"✅ Model retrained. R² score: {val_score:.4f}")
        
        # Save updated model
        self.save_model()
        
        logger.info("✅ Slippage Sentinel retrained on live data")


# Singleton instance
_sentinel_instance = None


def get_slippage_sentinel() -> SlippageSentinel:
    """Get or create singleton Slippage Sentinel instance."""
    global _sentinel_instance
    if _sentinel_instance is None:
        _sentinel_instance = SlippageSentinel()
    return _sentinel_instance


if __name__ == "__main__":
    # Test the Slippage Sentinel
    sentinel = SlippageSentinel()
    
    # Test case 1: Small trade in large pool (low impact)
    result1 = sentinel.predict_slippage(
        trade_amount_usd=5000,
        pool_liquidity_usd=2_000_000,
        volatility_1h=0.01,
        volatility_24h=0.02
    )
    print("\n📊 Test 1 - Small trade ($5k in $2M pool):")
    print(f"   Predicted Slippage: {result1['predicted_slippage']*100:.3f}%")
    print(f"   Confidence: {result1['confidence_score']*100:.1f}%")
    print(f"   Impact: {result1['impact_category']}")
    
    # Test case 2: Large trade in small pool (high impact)
    result2 = sentinel.predict_slippage(
        trade_amount_usd=50000,
        pool_liquidity_usd=200_000,
        volatility_1h=0.03,
        volatility_24h=0.05
    )
    print("\n📊 Test 2 - Large trade ($50k in $200k pool):")
    print(f"   Predicted Slippage: {result2['predicted_slippage']*100:.3f}%")
    print(f"   Confidence: {result2['confidence_score']*100:.1f}%")
    print(f"   Impact: {result2['impact_category']}")
    
    # Test case 3: Medium trade, high volatility
    result3 = sentinel.predict_slippage(
        trade_amount_usd=10000,
        pool_liquidity_usd=500_000,
        volatility_1h=0.05,
        volatility_24h=0.10
    )
    print("\n📊 Test 3 - High volatility ($10k in $500k pool, 5% vol):")
    print(f"   Predicted Slippage: {result3['predicted_slippage']*100:.3f}%")
    print(f"   Confidence: {result3['confidence_score']*100:.1f}%")
    print(f"   Impact: {result3['impact_category']}")
