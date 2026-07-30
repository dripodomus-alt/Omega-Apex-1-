"""
gas_oracle.py - Fetches live gas prices for the Polygon network.

This module provides a reliable way to get the current "fast" gas price,
ensuring that profitability calculations are based on real-time market conditions.
"""

import requests
from typing import Optional

# Polygon Gas Station is a reliable source for gas price estimates.
POLYGON_GAS_STATION_URL = "https://gasstation.polygon.technology/v2"


def get_live_gas_price_gwei() -> Optional[float]:
    """
    Fetches the current "fast" gas price from the Polygon Gas Station.

    Returns:
        The gas price in Gwei as a float, or None if the request fails.
    """
    try:
        response = requests.get(POLYGON_GAS_STATION_URL, timeout=5)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        # The "fast" price is recommended for arbitrage to ensure timely inclusion.
        fast_price_gwei = data.get("fast", {}).get("maxFee")

        if fast_price_gwei:
            return float(fast_price_gwei)
        else:
            print("[WARNING] Gas oracle response did not contain 'fast.maxFee' field.")
            return None

    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        print(f"[ERROR] Failed to fetch live gas price: {e}")
        return None