"""
APEX_OMEGA Liquidation Endpoint Tests
Tests liquidation hunting and executor endpoints
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


class TestLiquidationScanEndpoint:
    """Test liquidation scanning endpoint"""
    
    def test_liquidation_scan_basic(self):
        """Test basic liquidation scan endpoint"""
        response = requests.get(f"{BASE_URL}/api/liquidations/scan")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "timestamp" in data
        assert "liquidations_found" in data
        assert "total_profit_potential" in data
        assert "liquidations" in data
        assert "strategy" in data
        assert "message" in data
        
        # Verify strategy is correct
        assert data["strategy"] == "aave_v3_liquidation_hunting"
        
        # Verify liquidations is a list
        assert isinstance(data["liquidations"], list)
        
        print(f"Liquidations found: {data['liquidations_found']}")
        print(f"Total profit potential: ${data['total_profit_potential']}")
    
    def test_liquidation_scan_with_min_profit(self):
        """Test liquidation scan with min profit filter"""
        response = requests.get(f"{BASE_URL}/api/liquidations/scan?min_profit_usd=100")
        assert response.status_code == 200
        data = response.json()
        
        # All returned liquidations should have profit >= 100
        for liq in data["liquidations"]:
            assert liq["estimated_profit_usd"] >= 100, \
                f"Liquidation profit ${liq['estimated_profit_usd']} below threshold"


class TestLiquidationExecutorEndpoint:
    """Test liquidation executor contract endpoints"""
    
    def test_executor_info(self):
        """Test liquidation executor info endpoint"""
        response = requests.get(f"{BASE_URL}/api/liquidation-executor/info")
        assert response.status_code == 200
        data = response.json()
        
        # Verify deployment status
        assert "deployed" in data
        assert data["deployed"] == True, "Liquidation executor should be deployed"
        
        # Verify contract address
        assert "contract_address" in data
        assert data["contract_address"] == "0xEDa4ad19E6dc62dF5571629384043CEBaA1f999b"
        
        # Verify owner
        assert "owner" in data
        assert data["owner"].startswith("0x")
        
        # Verify network
        assert data["network"] == "Polygon"
        assert data["chain_id"] == 137
        
        # Verify features
        assert "features" in data
        features = data["features"]
        assert features["flash_loan_provider"] == "Balancer V2 (0% fee)"
        assert features["liquidation_protocol"] == "Aave V3"
        assert "QuickSwap V3" in features["supported_dexs"]
        assert "Uniswap V3" in features["supported_dexs"]
        
        print(f"Contract: {data['contract_address']}")
        print(f"Owner: {data['owner']}")
        print(f"Features: {features}")
    
    def test_supported_protocols(self):
        """Test supported protocols endpoint"""
        response = requests.get(f"{BASE_URL}/api/liquidation-executor/protocols")
        assert response.status_code == 200
        data = response.json()
        
        # Verify protocols list
        assert "protocols" in data
        protocols = data["protocols"]
        assert len(protocols) >= 4, "Should have at least 4 supported protocols"
        
        # Verify protocol structure
        for protocol in protocols:
            assert "id" in protocol
            assert "name" in protocol
            assert "type" in protocol
            assert "router" in protocol
            assert "default_fee" in protocol
            assert "description" in protocol
        
        # Verify specific protocols exist
        protocol_names = [p["name"] for p in protocols]
        assert "QuickSwap V3" in protocol_names
        assert "Uniswap V3" in protocol_names
        assert "SushiSwap" in protocol_names
        assert "QuickSwap V2" in protocol_names
        
        print(f"Supported protocols: {protocol_names}")


class TestLiquidationPayloadBuilder:
    """Test liquidation payload building endpoint"""
    
    def test_build_payload_missing_position(self):
        """Test build payload with missing position"""
        response = requests.post(
            f"{BASE_URL}/api/liquidation-executor/build-payload",
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return error for missing position
        assert "error" in data
        assert "position" in data["error"].lower()
    
    def test_build_payload_with_mock_position(self):
        """Test build payload with mock position data"""
        mock_position = {
            "user_address": "0x1234567890123456789012345678901234567890",
            "collateral_asset": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            "collateral_symbol": "WETH",
            "collateral_amount": 1.0,
            "collateral_value_usd": 2000.0,
            "debt_asset": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            "debt_symbol": "USDC",
            "debt_amount": 1500.0,
            "debt_value_usd": 1500.0,
            "health_factor": 0.95,
            "liquidation_threshold": 0.85,
            "liquidation_bonus_pct": 7.5,
            "max_liquidatable_debt_usd": 750.0,
            "liquidation_bonus_usd": 56.25,
            "estimated_profit_usd": 50.0,
            "flash_loan_needed_usd": 750.0,
            "is_executable": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/liquidation-executor/build-payload",
            json={"position": mock_position, "min_profit_bps": 50}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return payload or error (depending on contract state)
        # Either way, endpoint should respond
        print(f"Build payload response: {data}")


class TestLiquidationExecuteEndpoint:
    """Test liquidation execution endpoint"""
    
    def test_execute_dry_run(self):
        """Test liquidation execution in dry run mode"""
        response = requests.post(
            f"{BASE_URL}/api/liquidations/execute",
            params={
                "user_address": "0x1234567890123456789012345678901234567890",
                "dry_run": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return status (either not_liquidatable or dry_run result)
        assert "status" in data
        print(f"Execute response: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
