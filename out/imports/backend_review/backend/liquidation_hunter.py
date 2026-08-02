"""
APEX_OMEGA Liquidation Hunter
Find and execute profitable liquidations on Aave V3 (Polygon)

Strategy:
1. Monitor all open positions on Aave V3
2. Calculate health factors in real-time
3. Identify positions ready for liquidation (health factor < 1.0)
4. Calculate liquidation profitability (bonus - costs)
5. Execute via flash loan (capital-free)

Profit Sources:
- Liquidation bonus: 5-10% of collateral value
- Covered by borrower's collateral
- Risk-free profit!
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from web3 import Web3
from decimal import Decimal
from executor_registry import get_rpc_url

logger = logging.getLogger(__name__)


@dataclass
class LiquidatablePosition:
    """A position that can be liquidated for profit"""
    user_address: str
    collateral_asset: str
    collateral_symbol: str
    collateral_amount: float
    collateral_value_usd: float
    
    debt_asset: str
    debt_symbol: str
    debt_amount: float
    debt_value_usd: float
    
    health_factor: float
    liquidation_threshold: float
    liquidation_bonus_pct: float
    
    # Profitability
    max_liquidatable_debt_usd: float
    liquidation_bonus_usd: float
    estimated_profit_usd: float
    
    # Execution
    flash_loan_needed_usd: float
    is_executable: bool


class AaveLiquidationHunter:
    """
    Hunt for liquidation opportunities on Aave V3 (Polygon)
    
    How Aave Liquidations Work:
    1. User borrows assets using collateral
    2. If collateral value drops or debt increases, health factor < 1.0
    3. Liquidator can repay up to 50% of debt
    4. Liquidator receives collateral + liquidation bonus (5-10%)
    5. Profit = (collateral_value * bonus) - debt_repaid - gas
    
    Example:
    - User has 10 ETH collateral ($20,000)
    - User borrowed 15,000 USDC
    - ETH drops, health factor = 0.95 (LIQUIDATABLE)
    - Liquidator repays 7,500 USDC (50% of debt)
    - Liquidator receives $7,500 worth of ETH + 10% bonus = $8,250 in ETH
    - Profit: $8,250 - $7,500 = $750 (10% return!)
    """
    
    # Aave V3 Polygon Contracts
    AAVE_POOL = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"  # Aave V3 Pool
    AAVE_DATA_PROVIDER = "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654"  # Pool Data Provider
    AAVE_ORACLE = "0xb023e699F5a33916Ea823A16485e259257cA8Bd1"  # Price Oracle
    
    # Common assets on Polygon Aave V3
    ASSETS = {
        "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    }
    
    def __init__(self, rpc_url: str = None):
        if rpc_url is None:
            rpc_url = get_rpc_url('polygon')
        
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
        
        # Aave V3 Pool ABI (minimal for liquidation)
        self.pool_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "collateralAsset", "type": "address"},
                    {"internalType": "address", "name": "debtAsset", "type": "address"},
                    {"internalType": "address", "name": "user", "type": "address"},
                    {"internalType": "uint256", "name": "debtToCover", "type": "uint256"},
                    {"internalType": "bool", "name": "receiveAToken", "type": "bool"}
                ],
                "name": "liquidationCall",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
                "name": "getUserAccountData",
                "outputs": [
                    {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
                    {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
                    {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
                    {"internalType": "uint256", "name": "ltv", "type": "uint256"},
                    {"internalType": "uint256", "name": "healthFactor", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.pool_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.AAVE_POOL),
            abi=self.pool_abi
        )
        
        logger.info("🎯 Aave Liquidation Hunter initialized")
        logger.info(f"   Pool: {self.AAVE_POOL}")
        logger.info(f"   Network: Polygon (Chain ID: {self.w3.eth.chain_id})")
    
    def get_user_health_factor(self, user_address: str) -> Optional[float]:
        """
        Get user's health factor from Aave
        
        Health Factor:
        - > 1.0: Safe (collateralized)
        - = 1.0: At liquidation threshold
        - < 1.0: LIQUIDATABLE
        
        Formula: health_factor = (collateral_value * liquidation_threshold) / total_debt
        """
        try:
            account_data = self.pool_contract.functions.getUserAccountData(
                Web3.to_checksum_address(user_address)
            ).call()
            
            total_collateral_usd = account_data[0] / 1e8  # Base currency (USD) with 8 decimals
            total_debt_usd = account_data[1] / 1e8
            health_factor_raw = account_data[5]
            
            # Health factor is returned with 18 decimals
            health_factor = health_factor_raw / 1e18 if health_factor_raw > 0 else float('inf')
            
            return {
                "total_collateral_usd": total_collateral_usd,
                "total_debt_usd": total_debt_usd,
                "health_factor": health_factor,
                "is_liquidatable": health_factor < 1.0
            }
        except Exception as e:
            logger.error(f"Failed to get health factor for {user_address}: {e}")
            return None
    
    def scan_for_liquidations(
        self,
        user_addresses: List[str] = None,
        min_profit_usd: float = 10.0
    ) -> List[LiquidatablePosition]:
        """
        Scan Aave for liquidatable positions
        
        Args:
            user_addresses: Specific addresses to check (or scan top borrowers)
            min_profit_usd: Minimum profit to consider
            
        Returns:
            List of profitable liquidation opportunities
        """
        liquidations = []
        
        # If no addresses provided, we'd need to scan events/subgraph
        # For now, accept provided addresses
        if not user_addresses:
            logger.warning("No user addresses provided. In production, scan Aave events or use The Graph")
            return []
        
        logger.info(f"🔍 Scanning {len(user_addresses)} positions for liquidations...")
        
        for user_address in user_addresses:
            account_data = self.get_user_health_factor(user_address)
            
            if not account_data or not account_data["is_liquidatable"]:
                continue
            
            # Position is liquidatable!
            health_factor = account_data["health_factor"]
            total_collateral_usd = account_data["total_collateral_usd"]
            total_debt_usd = account_data["total_debt_usd"]
            
            # Calculate liquidation profitability
            # Can liquidate up to 50% of debt
            max_liquidatable_debt = total_debt_usd * 0.5
            
            # Liquidation bonus: typically 5-10% (use 7.5% average)
            liquidation_bonus_pct = 7.5
            liquidation_bonus_usd = max_liquidatable_debt * (liquidation_bonus_pct / 100)
            
            # Estimated profit (before gas)
            # Profit = bonus - flash_loan_fee - gas
            flash_loan_fee = max_liquidatable_debt * 0.0009  # 0.09% Aave flash loan
            gas_cost_usd = 0.50  # ~$0.50 on Polygon
            
            estimated_profit_usd = liquidation_bonus_usd - flash_loan_fee - gas_cost_usd
            
            if estimated_profit_usd >= min_profit_usd:
                position = LiquidatablePosition(
                    user_address=user_address,
                    collateral_asset="UNKNOWN",  # Would need to fetch from contract
                    collateral_symbol="UNKNOWN",
                    collateral_amount=0,
                    collateral_value_usd=total_collateral_usd,
                    debt_asset="UNKNOWN",
                    debt_symbol="UNKNOWN",
                    debt_amount=0,
                    debt_value_usd=total_debt_usd,
                    health_factor=health_factor,
                    liquidation_threshold=0.85,  # Typical
                    liquidation_bonus_pct=liquidation_bonus_pct,
                    max_liquidatable_debt_usd=max_liquidatable_debt,
                    liquidation_bonus_usd=liquidation_bonus_usd,
                    estimated_profit_usd=estimated_profit_usd,
                    flash_loan_needed_usd=max_liquidatable_debt,
                    is_executable=True
                )
                
                liquidations.append(position)
                
                logger.info(
                    f"💰 LIQUIDATION FOUND: {user_address[:10]}... | "
                    f"Health: {health_factor:.4f} | "
                    f"Debt: ${total_debt_usd:,.2f} | "
                    f"Profit: ${estimated_profit_usd:.2f}"
                )
        
        liquidations.sort(key=lambda x: x.estimated_profit_usd, reverse=True)
        
        logger.info(f"🎯 Found {len(liquidations)} profitable liquidations (profit > ${min_profit_usd})")
        
        return liquidations
    
    def execute_liquidation(
        self,
        position: LiquidatablePosition,
        dry_run: bool = True
    ) -> Dict:
        """
        Execute liquidation using flash loan
        
        Strategy:
        1. Flash loan debt amount from Balancer (free) or Aave (0.09%)
        2. Call Aave liquidationCall
        3. Receive collateral + bonus
        4. Swap collateral to debt asset
        5. Repay flash loan
        6. Keep profit
        
        Returns execution result
        """
        if dry_run:
            return {
                "status": "dry_run",
                "user": position.user_address,
                "debt_to_cover_usd": position.max_liquidatable_debt_usd,
                "expected_profit_usd": position.estimated_profit_usd,
                "message": "Liquidation payload would be built here"
            }
        
        # In production: Build and send actual transaction
        logger.warning("Live liquidation execution not implemented yet")
        return {"status": "not_implemented"}

    def get_stats(self) -> Dict:
        """
        Get statistics about liquidation hunting activity.
        
        Returns tracking stats (placeholder for now - will be populated during scanning).
        """
        return {
            'positions_scanned': 0,
            'unhealthy_positions': 0,
            'liquidation_candidates': 0,
            'total_value_at_risk': 0.0
        }
    
    async def scan_positions(self):
        """
        Async wrapper for scan_for_liquidations (for API compatibility).
        """
        return self.scan_for_liquidations()


# Global instance
_liquidation_hunter: Optional[AaveLiquidationHunter] = None


def get_liquidation_hunter() -> AaveLiquidationHunter:
    """Get or create liquidation hunter"""
    global _liquidation_hunter
    if _liquidation_hunter is None:
        _liquidation_hunter = AaveLiquidationHunter()
    return _liquidation_hunter
