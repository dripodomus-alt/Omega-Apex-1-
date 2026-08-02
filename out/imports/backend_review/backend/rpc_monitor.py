"""
🔱 APEX_OMEGA RPC MONITORING & AUTO-FAILOVER
Continuous endpoint health checking with automatic failover to best performing RPC
"""
import time
import logging
import asyncio
from typing import Dict, List, Optional
from web3 import Web3
from web3.providers import HTTPProvider
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class RPCHealthMonitor:
    """Monitors multiple RPC endpoints and selects the best one based on latency and block height"""
    
    def __init__(self):
        self.endpoints = {
            # Production endpoints from .env
            "Alchemy_Primary": os.getenv("POLYGON_HTTP", ""),
            "Alchemy_Secondary": os.getenv("ALCHEMY_HTTP_2", ""),
            "Infura_HTTP": os.getenv("INFURA_HTTP", ""),
            
            # Public fallbacks
            "Public_DRPC": "https://polygon.drpc.org",
            "Public_1RPC": "https://1rpc.io/matic",
            "Public_Llama": "https://polygon.llamarpc.com",
            "Public_Ankr": "https://rpc.ankr.com/polygon",
        }
        
        # Remove empty endpoints
        self.endpoints = {k: v for k, v in self.endpoints.items() if v}
        
        self.health_data: Dict[str, Dict] = {}
        self.current_best: Optional[str] = None
        self.last_scan_time: Optional[datetime] = None
        
    def test_endpoint(self, name: str, url: str) -> Optional[Dict]:
        """Test a single RPC endpoint for latency and block height"""
        start_time = time.time()
        
        try:
            w3 = Web3(HTTPProvider(url, request_kwargs={'timeout': 5}))
            
            if not w3.is_connected():
                logger.warning(f"❌ {name}: Connection refused")
                return None
            
            # Measure latency
            latency = (time.time() - start_time) * 1000
            
            # Verify chain ID
            chain_id = w3.eth.chain_id
            if chain_id != 137:
                logger.warning(f"⚠️ {name}: Wrong chain ID {chain_id}")
                return None
            
            # Get latest block
            latest_block = w3.eth.block_number
            
            return {
                'name': name,
                'url': url,
                'latency_ms': latency,
                'block': latest_block,
                'last_check': datetime.now(timezone.utc),
                'status': 'healthy'
            }
            
        except Exception as e:
            logger.error(f"❌ {name}: {str(e)[:50]}")
            return {
                'name': name,
                'url': url,
                'status': 'down',
                'error': str(e)[:100],
                'last_check': datetime.now(timezone.utc)
            }
    
    def scan_all_endpoints(self) -> List[Dict]:
        """Scan all configured endpoints and return results sorted by performance"""
        logger.info(f"🔱 Starting RPC health scan across {len(self.endpoints)} endpoints...")
        
        results = []
        for name, url in self.endpoints.items():
            result = self.test_endpoint(name, url)
            if result:
                results.append(result)
                self.health_data[name] = result
        
        # Filter healthy nodes only
        healthy_nodes = [r for r in results if r.get('status') == 'healthy']
        
        if not healthy_nodes:
            logger.error("🚨 CRITICAL: All RPC endpoints are down!")
            return []
        
        # Find highest block
        highest_block = max(n['block'] for n in healthy_nodes)
        
        # Sort by block height (desc) then latency (asc)
        healthy_nodes.sort(key=lambda x: (-x['block'], x['latency_ms']))
        
        # Log leaderboard
        logger.info("\n" + "="*80)
        logger.info("🏆 RPC ENDPOINT LEADERBOARD")
        logger.info("="*80)
        
        for i, node in enumerate(healthy_nodes):
            lag_warning = ""
            if node['block'] < highest_block:
                blocks_behind = highest_block - node['block']
                lag_warning = f" ⚠️ {blocks_behind} blocks behind"
            
            logger.info(
                f"#{i+1} | {node['latency_ms']:6.2f}ms | "
                f"Block: {node['block']} | {node['name']:<20}{lag_warning}"
            )
        
        # Update current best
        if healthy_nodes:
            self.current_best = healthy_nodes[0]['name']
            logger.info(f"\n✅ Selected RPC: {self.current_best} ({healthy_nodes[0]['latency_ms']:.2f}ms)")
        
        self.last_scan_time = datetime.now(timezone.utc)
        return healthy_nodes
    
    def get_best_endpoint(self) -> Optional[str]:
        """Get the URL of the currently best performing endpoint"""
        if not self.current_best or self.current_best not in self.health_data:
            # Run scan if no data
            results = self.scan_all_endpoints()
            if not results:
                return None
        
        best_data = self.health_data.get(self.current_best)
        return best_data['url'] if best_data else None
    
    def get_health_summary(self) -> Dict:
        """Get current health status of all endpoints"""
        return {
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'current_best': self.current_best,
            'total_endpoints': len(self.endpoints),
            'healthy_count': sum(1 for data in self.health_data.values() if data.get('status') == 'healthy'),
            'endpoints': self.health_data
        }


# Global instance
rpc_monitor = RPCHealthMonitor()


async def periodic_rpc_scan(interval_minutes: int = 15):
    """Background task to periodically scan RPC endpoints"""
    while True:
        try:
            logger.info(f"🔄 Starting periodic RPC scan (interval: {interval_minutes} min)...")
            rpc_monitor.scan_all_endpoints()
        except Exception as e:
            logger.error(f"Error in periodic RPC scan: {e}")
        
        # Wait for next scan
        await asyncio.sleep(interval_minutes * 60)
