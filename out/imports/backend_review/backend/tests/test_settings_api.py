"""
Test Settings Tab Backend APIs
Tests for Strategy Management and RPC Health endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://nexus-engine-v4.preview.emergentagent.com')


class TestStrategyEndpoints:
    """Tests for /api/strategies/* endpoints"""
    
    def test_get_strategy_status(self):
        """Test GET /api/strategies/status returns strategy manager status"""
        response = requests.get(f"{BASE_URL}/api/strategies/status", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        # Verify response structure
        assert 'running' in data
        assert 'strategies' in data
        assert 'lanes' in data
        assert 'config' in data
        
        # Verify strategies structure
        assert 'arbitrage' in data['strategies']
        assert 'liquidation' in data['strategies']
        
        # Verify arbitrage strategy fields
        arb = data['strategies']['arbitrage']
        assert 'enabled' in arb
        assert 'scans' in arb
        assert 'opportunities_found' in arb
        
        # Verify lanes structure
        assert 'total' in data['lanes']
        assert 'active' in data['lanes']
        assert 'assignments' in data['lanes']
        
        print(f"✅ Strategy status: running={data['running']}, lanes={data['lanes']['total']}")
    
    def test_update_strategy_config(self):
        """Test POST /api/strategies/config accepts config updates"""
        config = {
            "arbitrage_enabled": True,
            "liquidation_enabled": True,
            "num_lanes": 8,
            "min_profit_usd": 2.0,
            "scan_interval_seconds": 20
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategies/config",
            json=config,
            timeout=15
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'updated'
        assert 'config' in data
        
        # Verify config was applied
        assert data['config']['strategies']['arbitrage']['enabled'] == True
        assert data['config']['strategies']['liquidation']['enabled'] == True
        assert data['config']['config']['min_profit_usd'] == 2.0
        assert data['config']['config']['scan_interval_seconds'] == 20
        
        print(f"✅ Config updated: min_profit=${data['config']['config']['min_profit_usd']}")
    
    def test_start_strategies(self):
        """Test POST /api/strategies/start starts strategies"""
        config = {
            "arbitrage_enabled": True,
            "liquidation_enabled": False,
            "num_lanes": 4
        }
        
        response = requests.post(
            f"{BASE_URL}/api/strategies/start",
            json=config,
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'started'
        assert data['config']['running'] == True
        assert data['config']['lanes']['active'] > 0
        
        print(f"✅ Strategies started: {data['config']['lanes']['active']} lanes active")
    
    def test_stop_strategies(self):
        """Test POST /api/strategies/stop stops strategies"""
        response = requests.post(
            f"{BASE_URL}/api/strategies/stop",
            timeout=30
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'stopped'
        assert data['stats']['running'] == False
        assert data['stats']['lanes']['active'] == 0
        
        print(f"✅ Strategies stopped successfully")


class TestRPCEndpoints:
    """Tests for /api/rpc/* endpoints"""
    
    def test_get_rpc_health(self):
        """Test GET /api/rpc/health returns RPC health summary"""
        response = requests.get(f"{BASE_URL}/api/rpc/health", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        # Verify response structure
        assert 'current_best' in data
        assert 'total_endpoints' in data
        assert 'healthy_count' in data
        assert 'endpoints' in data
        
        # Verify we have endpoints
        assert data['total_endpoints'] > 0
        assert data['healthy_count'] > 0
        assert data['current_best'] is not None
        
        # Verify endpoint data structure
        for name, endpoint in data['endpoints'].items():
            assert 'status' in endpoint
            assert 'last_check' in endpoint
            if endpoint['status'] == 'healthy':
                assert 'latency_ms' in endpoint
                assert 'block' in endpoint
        
        print(f"✅ RPC health: {data['healthy_count']}/{data['total_endpoints']} healthy, best={data['current_best']}")
    
    def test_trigger_rpc_scan(self):
        """Test POST /api/rpc/scan triggers RPC scan"""
        response = requests.post(f"{BASE_URL}/api/rpc/scan", timeout=30)
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] == True
        assert 'scanned' in data
        assert 'current_best' in data
        assert 'results' in data
        
        # Verify scan results
        assert data['scanned'] > 0
        assert len(data['results']) > 0
        
        # Verify result structure
        for result in data['results']:
            assert 'name' in result
            assert 'status' in result
            if result['status'] == 'healthy':
                assert 'latency_ms' in result
                assert 'block' in result
        
        print(f"✅ RPC scan complete: {data['scanned']} endpoints, best={data['current_best']}")
    
    def test_get_best_rpc(self):
        """Test GET /api/rpc/best returns best RPC endpoint"""
        response = requests.get(f"{BASE_URL}/api/rpc/best", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert 'current_best' in data
        assert 'url' in data
        
        # Verify URL is valid
        assert data['url'].startswith('https://')
        
        print(f"✅ Best RPC: {data['current_best']} - {data['url'][:50]}...")


class TestOtherTabsAPIs:
    """Tests for APIs used by other tabs to ensure they still work"""
    
    def test_bot_config(self):
        """Test GET /api/bot/config for Dashboard tab"""
        response = requests.get(f"{BASE_URL}/api/bot/config", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert 'rpc_configured' in data
        assert 'min_profit_threshold' in data
        print(f"✅ Bot config: RPC={data['rpc_configured']}")
    
    def test_arbitrage_config(self):
        """Test GET /api/arbitrage/config for Calculator tab"""
        response = requests.get(f"{BASE_URL}/api/arbitrage/config", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert 'minProfitUsd' in data
        assert 'flashLoanFeeBps' in data
        assert 'gasPriceGwei' in data
        print(f"✅ Arb config: minProfit=${data['minProfitUsd']}, gas={data['gasPriceGwei']}gwei")
    
    def test_executor_stats(self):
        """Test GET /api/executor/stats for Dashboard tab"""
        response = requests.get(f"{BASE_URL}/api/executor/stats", timeout=15)
        assert response.status_code == 200
        
        data = response.json()
        assert 'mode' in data or 'isRunning' in data or 'stats' in data
        print(f"✅ Executor stats retrieved")
    
    def test_pool_prices(self):
        """Test GET /api/pool-prices for Pools tab"""
        response = requests.get(f"{BASE_URL}/api/pool-prices", timeout=30)
        assert response.status_code == 200
        
        data = response.json()
        assert 'pools' in data
        assert 'timestamp' in data
        print(f"✅ Pool prices: {len(data.get('pools', []))} pools")
    
    def test_liquidations_scan(self):
        """Test GET /api/liquidations/scan for Liquidations tab"""
        response = requests.get(f"{BASE_URL}/api/liquidations/scan", timeout=30)
        assert response.status_code == 200
        
        data = response.json()
        assert 'liquidations_found' in data
        assert 'liquidations' in data
        print(f"✅ Liquidations: {data['liquidations_found']} found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
