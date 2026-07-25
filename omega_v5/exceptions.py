# ==============================================================================
# exceptions.py -- Centralized custom exceptions for the application.
# ==============================================================================
class PriceUnavailable(Exception):
    """Custom exception for when a token price cannot be found."""
    pass