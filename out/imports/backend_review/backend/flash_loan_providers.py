"""
Flash Loan Provider Integration
Supports Aave V3 and Balancer Vault with smart provider selection
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import IntEnum
from web3 import Web3

logger = logging.getLogger(__name__)


class FlashLoanProvider(IntEnum):
    """Flash loan providers"""
    AAVE_V3 = 1
    BALANCER_VAULT = 2


@dataclass
class FlashLoanConfig:
    """Flash loan provider configuration"""
    provider: FlashLoanProvider
    name: str
    address: str
    fee_bps: int  # Basis points (e.g., 9 for 0.09%)
    max_loan_usd: float
    available_tokens: List[str]


# Polygon Flash Loan Providers
FLASH_LOAN_PROVIDERS = {
    FlashLoanProvider.AAVE_V3: FlashLoanConfig(
        provider=FlashLoanProvider.AAVE_V3,
        name="Aave V3",
        address="0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        fee_bps=9,  # 0.09%
        max_loan_usd=10_000_000,  # $10M typical
        available_tokens=[
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
            "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
        ]
    ),
    FlashLoanProvider.BALANCER_VAULT: FlashLoanConfig(
        provider=FlashLoanProvider.BALANCER_VAULT,
        name="Balancer Vault",
        address="0xBA12222222228d8Ba445958a75a0704d566BF2C8",
        fee_bps=0,  # FREE! 0% fee
        max_loan_usd=50_000_000,  # $50M+ capacity
        available_tokens=[
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
            "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
            "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",  # AAVE
            "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",  # LINK
            "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",  # BAL
        ]
    )
}


class FlashLoanSelector:
    """
    Smart flash loan provider selection
    Chooses optimal provider(s) based on fees and profit
    """
    
    def __init__(self):
        self.providers = FLASH_LOAN_PROVIDERS
    
    def select_providers(
        self,
        borrow_token: str,
        loan_amount_usd: float,
        expected_profit_usd: float,
        gas_cost_usd: float
    ) -> List[FlashLoanConfig]:
        """
        Select flash loan provider(s) for arbitrage
        
        Strategy:
        1. Always prefer Balancer (FREE)
        2. Use Aave if Balancer doesn't support token
        3. Fire BOTH if profit is high enough (2x extraction)
        
        Args:
            borrow_token: Token address to borrow
            loan_amount_usd: Flash loan size in USD
            expected_profit_usd: Expected profit before flash loan fees
            gas_cost_usd: Gas cost for execution
            
        Returns:
            List of providers to use (can be multiple for dual execution)
        """
        borrow_token = borrow_token.lower()
        selected = []
        
        # Check Balancer (FREE - always check first)
        balancer = self.providers[FlashLoanProvider.BALANCER_VAULT]
        if self._supports_token(balancer, borrow_token):
            balancer_profit = expected_profit_usd - gas_cost_usd  # No flash loan fee!
            
            if balancer_profit > 0:
                selected.append(balancer)
                logger.info(f"✅ Balancer selected: FREE flash loan, net profit ${balancer_profit:.2f}")
        
        # Check Aave
        aave = self.providers[FlashLoanProvider.AAVE_V3]
        if self._supports_token(aave, borrow_token):
            aave_fee = loan_amount_usd * aave.fee_bps / 10000
            aave_profit = expected_profit_usd - aave_fee - gas_cost_usd
            
            if aave_profit > 0:
                # Add Aave if:
                # 1. Balancer not available, OR
                # 2. Profit high enough to fire both (dual extraction)
                if not selected:
                    selected.append(aave)
                    logger.info(f"✅ Aave selected: ${aave_fee:.2f} fee, net profit ${aave_profit:.2f}")
                elif aave_profit > 5:  # Fire both if Aave still profitable with >$5
                    selected.append(aave)
                    logger.info(f"🔥 DUAL EXECUTION: Firing both Balancer AND Aave!")
                    logger.info(f"   Balancer profit: ${expected_profit_usd - gas_cost_usd:.2f}")
                    logger.info(f"   Aave profit: ${aave_profit:.2f}")
                    logger.info(f"   Total extraction: ${expected_profit_usd - gas_cost_usd + aave_profit:.2f}")
        
        if not selected:
            logger.warning(f"No profitable flash loan provider for ${expected_profit_usd:.2f} profit")
        
        return selected
    
    def _supports_token(self, provider: FlashLoanConfig, token: str) -> bool:
        """Check if provider supports token"""
        token_lower = token.lower()
        return any(t.lower() == token_lower for t in provider.available_tokens)
    
    def calculate_net_profit(
        self,
        provider: FlashLoanConfig,
        loan_amount_usd: float,
        gross_profit_usd: float,
        gas_cost_usd: float
    ) -> float:
        """Calculate net profit after flash loan fee and gas"""
        flash_fee = loan_amount_usd * provider.fee_bps / 10000
        return gross_profit_usd - flash_fee - gas_cost_usd
    
    def get_execution_plan(
        self,
        borrow_token: str,
        loan_amount_usd: float,
        expected_profit_usd: float,
        gas_cost_usd: float
    ) -> Dict:
        """
        Get complete execution plan with provider details
        
        Returns:
            {
                'providers': [FlashLoanConfig, ...],
                'total_profit': float,
                'execution_count': int,
                'details': {
                    'balancer': {'fee': 0, 'profit': X},
                    'aave': {'fee': Y, 'profit': Z}
                }
            }
        """
        providers = self.select_providers(borrow_token, loan_amount_usd, expected_profit_usd, gas_cost_usd)
        
        details = {}
        total_profit = 0
        
        for provider in providers:
            fee = loan_amount_usd * provider.fee_bps / 10000
            profit = expected_profit_usd - fee - gas_cost_usd
            
            details[provider.name.lower().replace(' ', '_')] = {
                'provider': provider.name,
                'address': provider.address,
                'fee_bps': provider.fee_bps,
                'fee_usd': fee,
                'net_profit': profit,
                'gas_cost': gas_cost_usd
            }
            
            total_profit += profit
        
        return {
            'providers': providers,
            'total_profit': total_profit,
            'execution_count': len(providers),
            'should_execute': len(providers) > 0,
            'dual_execution': len(providers) > 1,
            'details': details
        }


# Balancer Vault Flash Loan ABI
BALANCER_VAULT_FLASH_LOAN_ABI = [
    {
        "inputs": [
            {"internalType": "contract IFlashLoanRecipient", "name": "recipient", "type": "address"},
            {"internalType": "contract IERC20[]", "name": "tokens", "type": "address[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
            {"internalType": "bytes", "name": "userData", "type": "bytes"}
        ],
        "name": "flashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Aave V3 Pool Flash Loan ABI
AAVE_V3_POOL_FLASH_LOAN_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "receiverAddress", "type": "address"},
            {"internalType": "address[]", "name": "assets", "type": "address[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
            {"internalType": "uint256[]", "name": "modes", "type": "uint256[]"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "bytes", "name": "params", "type": "bytes"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"}
        ],
        "name": "flashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


def build_balancer_flash_loan_calldata(
    recipient: str,
    tokens: List[str],
    amounts: List[int],
    user_data: bytes
) -> bytes:
    """
    Build calldata for Balancer Vault flash loan
    
    Args:
        recipient: Contract that will receive the flash loan
        tokens: List of token addresses to borrow
        amounts: List of amounts (in wei)
        user_data: Encoded swap data to execute
    """
    w3 = Web3()
    vault = w3.eth.contract(
        address=FLASH_LOAN_PROVIDERS[FlashLoanProvider.BALANCER_VAULT].address,
        abi=BALANCER_VAULT_FLASH_LOAN_ABI
    )
    
    return vault.encodeABI(
        fn_name='flashLoan',
        args=[recipient, tokens, amounts, user_data]
    )


def build_aave_flash_loan_calldata(
    receiver: str,
    assets: List[str],
    amounts: List[int],
    params: bytes
) -> bytes:
    """
    Build calldata for Aave V3 flash loan
    
    Args:
        receiver: Contract that will receive the flash loan
        assets: List of token addresses to borrow
        amounts: List of amounts (in wei)
        params: Encoded swap data to execute
    """
    w3 = Web3()
    pool = w3.eth.contract(
        address=FLASH_LOAN_PROVIDERS[FlashLoanProvider.AAVE_V3].address,
        abi=AAVE_V3_POOL_FLASH_LOAN_ABI
    )
    
    # modes: 0 = no debt, revert if not repaid
    modes = [0] * len(assets)
    
    return pool.encodeABI(
        fn_name='flashLoan',
        args=[receiver, assets, amounts, modes, receiver, params, 0]
    )


# Global selector instance
flash_loan_selector = FlashLoanSelector()
