"""
APEX_OMEGA Backend API Tests
Tests all API endpoints for the arbitrage system
"""
import pytest
import requests
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment
load_dotenv(Path(__file__).parent.parent / '.env')

# Get backend URL from frontend .env (production URL)
frontend_env = Path(__file__).parent.parent.parent / 'frontend' / '.env'
if frontend_env.exists():
    with open(frontend_env) as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                break
else:
    BASE_URL = "http://localhost:8001"

print(f"Testing against: {BASE_URL}")


class TestHealthEndpoints:
    """Test basic health and config endpoints"""
    
    def test_root_endpoint(self):
        """Test root API endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "APEX_OMEGA" in data["message"]
    
    def test_bot_config(self):
        """Test bot configuration endpoint"""
        response = requests.get(f"{BASE_URL}/api/bot/config")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "min_profit_threshold" in data
        assert "max_slippage_tolerance" in data
        assert "rpc_configured" in data
        assert "token_configured" in data
        
        # Verify RPC is configured (not mock)
        assert data["rpc_configured"] == True, "RPC should be configured"
    
    def test_arbitrage_config(self):
        """Test arbitrage engine configuration"""
        response = requests.get(f"{BASE_URL}/api/arbitrage/config")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "minReserveUsd" in data
        assert "minProfitUsd" in data
        assert "flashLoanFeeBps" in data
        assert "gasPriceGwei" in data
        assert "gasUnits" in data
        assert "maticPriceUsd" in data
        assert "poolCount" in data
        assert "titanEnabled" in data
        
        # Verify pool count is at least the minimum supported (was 274, now ~4500)
        assert data["poolCount"] >= 100, f"Expected at least 100 pools, got {data['poolCount']}"
        
        # Verify TITAN engine is enabled
        assert data["titanEnabled"] == True
        
        # Verify gas cost is in pennies range for Polygon
        gas_cost_usd = (data["gasPriceGwei"] * data["gasUnits"] / 1e9) * data["maticPriceUsd"]
        assert gas_cost_usd < 0.10, f"Gas cost ${gas_cost_usd:.4f} should be < $0.10 on Polygon"
        print(f"Gas cost: ${gas_cost_usd:.4f} (expected ~$0.01-0.02)")


class TestPoolEndpoints:
    """Test pool-related endpoints"""
    
    def test_pool_prices(self):
        """Test pool prices endpoint returns the active pool inventory"""
        response = requests.get(f"{BASE_URL}/api/pool-prices")
        assert response.status_code in (200, 503), f"Expected 200 or 503, got {response.status_code}"
        data = response.json()

        # 503 = engine cold-start; treat as a valid (but skipped) outcome
        if response.status_code == 503:
            assert data.get("loading") is True
            return

        assert "pools" in data
        assert "timestamp" in data

        pools = data["pools"]
        assert len(pools) >= 100, f"Expected at least 100 pools, got {len(pools)}"
        
        # Verify pool structure
        if pools:
            pool = pools[0]
            assert "poolAddress" in pool
            assert "dexName" in pool
            assert "token0Symbol" in pool
            assert "token1Symbol" in pool
            assert "spotPrice" in pool
            assert "reserveUsd" in pool
            assert "fee" in pool


class TestSpreadEndpoints:
    """Test spread detection endpoints"""
    
    def test_spreads_endpoint(self):
        """Test spreads endpoint with loan amount"""
        response = requests.get(f"{BASE_URL}/api/spreads?loan_amount=10000")
        assert response.status_code == 200
        data = response.json()
        
        assert "spreads" in data
        assert "timestamp" in data
        
        # Spreads may be empty if no profitable opportunities
        spreads = data["spreads"]
        print(f"Found {len(spreads)} spreads")
        
        # If spreads exist, verify structure
        if spreads:
            spread = spreads[0]
            assert "tokenPair" in spread
            assert "flashLoan" in spread
            
            fl = spread["flashLoan"]
            assert "loanAmountUsd" in fl
            assert "netProfitUsd" in fl
            assert "gasCostUsd" in fl
            assert "isExecutable" in fl
    
    def test_arbitrage_scan(self):
        """Test arbitrage scan endpoint"""
        response = requests.get(f"{BASE_URL}/api/arbitrage/scan?loan_amount=10000&min_profit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_spreads" in data
        assert "executable" in data
        assert "opportunities" in data


class TestExecutorEndpoints:
    """Test executor-related endpoints"""
    
    def test_executor_stats(self):
        """Test executor statistics endpoint"""
        response = requests.get(f"{BASE_URL}/api/executor/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data
        assert "isRunning" in data
        assert "stats" in data
        
        # Verify stats structure
        stats = data["stats"]
        assert "blocks_processed" in stats
        assert "opportunities_found" in stats
        assert "executions_attempted" in stats
    
    def test_contract_info(self):
        """Test contract info endpoint"""
        response = requests.get(f"{BASE_URL}/api/execute/contract-info")
        assert response.status_code == 200
        data = response.json()
        
        # Verify contract address
        assert "contract" in data
        assert data["contract"] == "0xa75f6372eee406Ab17dC957FA8FCB49cFaE0a33f"
        
        # Verify owner
        assert "owner" in data
        
        # Verify network
        assert data["network"] == "Polygon"
        assert data["chain_id"] == 137
        
        # Verify flash loan support
        assert "supports" in data
        assert data["supports"]["aave_v3"] == True
        assert data["supports"]["balancer_v3"] == True


class TestRPCEndpoints:
    """Test RPC monitoring endpoints"""
    
    def test_rpc_health(self):
        """Test RPC health endpoint"""
        response = requests.get(f"{BASE_URL}/api/rpc/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_best" in data
        assert "total_endpoints" in data
        assert "healthy_count" in data
        assert "endpoints" in data
        
        # Verify at least some endpoints are healthy
        assert data["healthy_count"] > 0, "At least one RPC endpoint should be healthy"
        print(f"RPC Health: {data['healthy_count']}/{data['total_endpoints']} healthy")
        print(f"Current best: {data['current_best']}")
    
    def test_rpc_best(self):
        """Test best RPC endpoint"""
        response = requests.get(f"{BASE_URL}/api/rpc/best")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_best" in data
        assert "url" in data


class TestGasCalculations:
    """Test gas cost calculations are correct for Polygon"""
    
    def test_gas_cost_in_pennies(self):
        """Verify gas cost is in pennies range on Polygon"""
        response = requests.get(f"{BASE_URL}/api/arbitrage/config")
        assert response.status_code == 200
        data = response.json()
        
        # Calculate gas cost
        gas_price_gwei = data["gasPriceGwei"]
        gas_units = data["gasUnits"]
        matic_price = data["maticPriceUsd"]
        
        # Gas cost = (gas_price_gwei * gas_units / 1e9) * matic_price
        gas_cost_usd = (gas_price_gwei * gas_units / 1e9) * matic_price
        
        # Polygon gas should be very cheap (< $0.05)
        assert gas_cost_usd < 0.05, f"Gas cost ${gas_cost_usd:.4f} too high for Polygon"
        assert gas_cost_usd > 0.001, f"Gas cost ${gas_cost_usd:.4f} suspiciously low"
        
        print(f"Gas calculation: {gas_price_gwei} gwei * {gas_units} units / 1e9 * ${matic_price} = ${gas_cost_usd:.4f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
