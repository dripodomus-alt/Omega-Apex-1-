"""
Unified Strategy Manager
Runs Arbitrage Executor + Liquidation Hunter simultaneously
Supports 1-32 parallel lanes
"""

import asyncio
import logging
import time
import os
from typing import Dict, List
from enum import Enum
from dataclasses import dataclass
from execution_governance import get_minimum_net_profit_usd

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    ARBITRAGE = "arbitrage"
    LIQUIDATION = "liquidation"
    BOTH = "both"


class LaneType(str, Enum):
    BLUECHIP = "bluechip"  # Lanes 1-8: WMATIC, WETH, WBTC, Stablecoins
    MIDCAP = "midcap"      # Lanes 9-24: Top 500 tokens by TVL
    LONGTAIL = "longtail"  # Lanes 25-32: New pairs, Algebra ticks


@dataclass
class StrategyConfig:
    """Configuration for strategy execution"""
    arbitrage_enabled: bool = False
    liquidation_enabled: bool = False
    num_lanes: int = 4
    lane_assignments: Dict[int, LaneType] = None
    min_profit_usd: float = get_minimum_net_profit_usd()
    scan_interval_seconds: int = 10
    
    def __post_init__(self):
        self.min_profit_usd = max(float(self.min_profit_usd), get_minimum_net_profit_usd())
        if self.lane_assignments is None:
            # Default: 4 lanes, all midcap
            self.lane_assignments = {
                i: LaneType.MIDCAP for i in range(1, self.num_lanes + 1)
            }


class StrategyManager:
    """
    Manages multiple strategies running simultaneously
    32-lane architecture for parallel execution
    """
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or StrategyConfig()
        self.running = False
        self.tasks = []
        self.stats = {
            'arbitrage': {
                'scans': 0,
                'opportunities_found': 0,
                'executions': 0,
                'total_profit_usd': 0
            },
            'liquidation': {
                'scans': 0,
                'opportunities_found': 0,
                'executions': 0,
                'total_profit_usd': 0
            },
            'lanes': {
                i: {'active': False, 'type': self.config.lane_assignments.get(i, LaneType.MIDCAP)}
                for i in range(1, self.config.num_lanes + 1)
            }
        }
    
    async def start(self):
        """Start all enabled strategies"""
        if self.running:
            logger.warning("Strategy manager already running")
            return
        
        self.running = True
        logger.info(f"🔱 Starting strategy manager with {self.config.num_lanes} lanes")
        
        # Start arbitrage if enabled
        if self.config.arbitrage_enabled:
            task = asyncio.create_task(self._run_arbitrage_strategy())
            self.tasks.append(task)
            logger.info("✅ Arbitrage executor started")
        
        # Start liquidation if enabled
        if self.config.liquidation_enabled:
            task = asyncio.create_task(self._run_liquidation_strategy())
            self.tasks.append(task)
            logger.info("✅ Liquidation hunter started")
        
        # Activate lanes
        for lane_num in range(1, self.config.num_lanes + 1):
            self.stats['lanes'][lane_num]['active'] = True
        
        logger.info(f"🚀 Strategy manager LIVE - {len(self.tasks)} strategies active")
    
    async def stop(self):
        """Stop all running strategies"""
        if not self.running:
            return
        
        self.running = False
        logger.info("⏸️  Stopping strategy manager...")
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        
        # Deactivate lanes
        for lane_num in self.stats['lanes']:
            self.stats['lanes'][lane_num]['active'] = False
        
        logger.info("✅ Strategy manager stopped")
    
    async def _run_arbitrage_strategy(self):
        """Arbitrage executor loop"""
        from arbitrage_engine import get_arbitrage_engine
        
        engine = get_arbitrage_engine()
        
        while self.running:
            try:
                # Scan for arbitrage opportunities
                logger.debug("🔍 Scanning for arbitrage...")
                spreads = engine.scan_for_spreads(loan_amount_usd=10000)
                
                self.stats['arbitrage']['scans'] += 1
                self.stats['arbitrage']['opportunities_found'] += len(spreads)
                
                # Execute profitable opportunities
                for spread in spreads:
                    if spread.flash_loan.net_profit_usd >= self.config.min_profit_usd:
                        logger.info(f"💰 Arbitrage opportunity: {spread.token_pair} - ${spread.flash_loan.net_profit_usd:.2f}")
                        # TODO: Execute via smart contract
                        # self.stats['arbitrage']['executions'] += 1
                        # self.stats['arbitrage']['total_profit_usd'] += spread.flash_loan.net_profit_usd
                
                # Wait before next scan
                await asyncio.sleep(self.config.scan_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Arbitrage error: {e}")
                await asyncio.sleep(5)
    
    async def _run_liquidation_strategy(self):
        """Liquidation hunter loop"""
        from liquidation_hunter import get_live_liquidation_hunter
        
        hunter = get_live_liquidation_hunter()
        
        while self.running:
            try:
                # Scan for liquidation opportunities
                logger.debug("🔍 Scanning for liquidations...")
                liquidations = hunter.scan_liquidations()
                
                self.stats['liquidation']['scans'] += 1
                self.stats['liquidation']['opportunities_found'] += len(liquidations)
                
                # Log profitable liquidations
                for liq in liquidations:
                    if liq.get('estimated_profit_usd', 0) >= self.config.min_profit_usd:
                        logger.info(f"💎 Liquidation opportunity: {liq.get('collateral_symbol')}/{liq.get('debt_symbol')} - ${liq.get('estimated_profit_usd', 0):.2f}")
                
                # Wait before next scan
                await asyncio.sleep(self.config.scan_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Liquidation error: {e}")
                await asyncio.sleep(5)
    
    def get_stats(self) -> Dict:
        """Get current strategy statistics with EXACT pool data"""
        active_lanes = sum(1 for lane in self.stats['lanes'].values() if lane['active'])
        
        # Get EXACT pool counts
        try:
            from arbitrage_engine import get_arbitrage_engine
            engine = get_arbitrage_engine()
            pools_loaded = len(engine.pools)
            pools_loading = getattr(engine, 'pools_loading', False)
            
            # Count by DEX
            dex_counts = {}
            for pool in engine.pools.values():
                dex = pool.dex_name
                dex_counts[dex] = dex_counts.get(dex, 0) + 1
        except:
            pools_loaded = 0
            pools_loading = True
            dex_counts = {}
        
        return {
            'running': self.running,
            'strategies': {
                'arbitrage': {
                    'enabled': self.config.arbitrage_enabled,
                    **self.stats['arbitrage']
                },
                'liquidation': {
                    'enabled': self.config.liquidation_enabled,
                    **self.stats['liquidation']
                }
            },
            'pools_exact_data': {
                'total_loaded': pools_loaded,
                'loading': pools_loading,
                'by_dex': dex_counts,
                'protocols': 'V2 (xy=k), V3 (tick-walking), Balancer (weighted), Curve (StableSwap)',
                'data_source': 'EXACT Web3 on-chain reserves - NO estimates'
            },
            'contracts': {
                'c1_kinetic_trident': '0xAF54D81835F811F1D4aB35c5856DDAE8834cdDA2',
                'c2_ultimate_arbitrage': '0xa75f6372eee406Ab17dC957FA8FCB49cFaE0a33f',
                'liquidation_executor': '0xEDa4ad19E6dc62dF5571629384043CEBaA1f999b',
                'aave_v3_pool': '0x794a61358D6845594F94dc1DB02A252b5b4814aD'
            },
            'lanes': {
                'total': self.config.num_lanes,
                'active': active_lanes,
                'assignments': {
                    str(num): {
                        'type': lane['type'].value,
                        'active': lane['active']
                    }
                    for num, lane in self.stats['lanes'].items()
                }
            },
            'config': {
                'min_profit_usd': self.config.min_profit_usd,
                'scan_interval_seconds': self.config.scan_interval_seconds
            }
        }
    
    def update_config(self, new_config: Dict):
        """Update strategy configuration"""
        if 'arbitrage_enabled' in new_config:
            self.config.arbitrage_enabled = new_config['arbitrage_enabled']
        if 'liquidation_enabled' in new_config:
            self.config.liquidation_enabled = new_config['liquidation_enabled']
        if 'num_lanes' in new_config:
            self.config.num_lanes = new_config['num_lanes']
        if 'min_profit_usd' in new_config:
            self.config.min_profit_usd = max(float(new_config['min_profit_usd']), get_minimum_net_profit_usd())
        if 'scan_interval_seconds' in new_config:
            self.config.scan_interval_seconds = new_config['scan_interval_seconds']
        
        logger.info(f"✅ Config updated: {new_config}")


# Global strategy manager instance
_strategy_manager = None


def get_strategy_manager() -> StrategyManager:
    """Get or create strategy manager singleton"""
    global _strategy_manager
    if _strategy_manager is None:
        _strategy_manager = StrategyManager()
    return _strategy_manager
