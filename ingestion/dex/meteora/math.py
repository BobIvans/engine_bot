"""
ingestion/dex/meteora/math.py

Meteora DLMM Math - Pure math functions for bin calculations.

PR-U.3

All functions are pure (no I/O).
"""
from decimal import Decimal, getcontext
from typing import Tuple


# Set high precision for decimal operations
getcontext().prec = 80

# Meteora bin ID offset - allows representing prices below 1
# In Meteora, price = 1 corresponds to bin_id = BIN_ID_OFFSET
# This offset fits within i32 range
BIN_ID_OFFSET = 2**23  # 8388608


class MeteoraMath:
    """
    Pure math functions for Meteora DLMM.
    
    PR-U.3
    
    The price formula is:
        price = (1 + bin_step/10000)^(active_id - BIN_ID_OFFSET)
    
    This allows representing prices both above and below 1.0.
    """
    
    @staticmethod
    def get_price_from_id(
        active_id: int,
        bin_step: int,
        decimals_x: int,
        decimals_y: int,
    ) -> float:
        """
        Convert bin ID to real price.
        
        Formula:
        Price_raw = (1 + bin_step/10000)^(active_id - BIN_ID_OFFSET)
        Price_real = Price_raw × 10^(decimals_x - decimals_y)
        
        Args:
            active_id: Active bin ID (can be negative relative to offset)
            bin_step: Bin step (in basis points, e.g., 20 for 0.2%)
            decimals_x: Decimals of token X
            decimals_y: Decimals of token Y
            
        Returns:
            Price of token X in terms of token Y
        """
        if bin_step <= 0:
            raise ValueError("bin_step must be positive")
        
        # Calculate offset-adjusted bin ID
        adjusted_id = active_id - BIN_ID_OFFSET
        
        # Base = 1 + bin_step/10000
        base = Decimal(1) + Decimal(bin_step) / Decimal(10000)
        
        # Price_raw = base^adjusted_id
        # Use Decimal for high precision
        price_raw = base ** Decimal(adjusted_id)
        
        # Adjust for decimals
        decimal_adjustment = Decimal(10) ** (decimals_x - decimals_y)
        price_real = price_raw * decimal_adjustment
        
        return float(price_real)
    
    @staticmethod
    def get_id_from_price(
        price: float,
        bin_step: int,
        decimals_x: int,
        decimals_y: int,
    ) -> int:
        """
        Convert real price to bin ID (inverse of get_price_from_id).
        
        Formula:
        adjusted_id = log_base(price_raw)
        active_id = adjusted_id + BIN_ID_OFFSET
        where base = 1 + bin_step/10000
        
        Args:
            price: Price of token X in terms of token Y
            bin_step: Bin step (in basis points)
            decimals_x: Decimals of token X
            decimals_y: Decimals of token Y
            
        Returns:
            Nearest bin ID
        """
        if price <= 0:
            raise ValueError("price must be positive")
        
        # Adjust for decimals
        decimal_adjustment = Decimal(10) ** (decimals_y - decimals_x)
        price_raw = Decimal(price) * decimal_adjustment
        
        # Base = 1 + bin_step/10000
        base = Decimal(1) + Decimal(bin_step) / Decimal(10000)
        
        # adjusted_id = log_base(price_raw) = ln(price_raw) / ln(base)
        adjusted_id = (price_raw.ln()) / (base.ln())
        
        # Add offset to get actual bin ID
        active_id = int(round(adjusted_id)) + BIN_ID_OFFSET
        
        return active_id
    
    @staticmethod
    def get_bin_range_price(
        lower_id: int,
        upper_id: int,
        bin_step: int,
        decimals_x: int,
        decimals_y: int,
    ) -> Tuple[float, float]:
        """
        Get price range for a bin interval.
        
        Args:
            lower_id: Lower bin ID
            upper_id: Upper bin ID
            bin_step: Bin step
            decimals_x: Decimals of token X
            decimals_y: Decimals of token Y
            
        Returns:
            Tuple of (lower_price, upper_price)
        """
        lower_price = MeteoraMath.get_price_from_id(
            lower_id, bin_step, decimals_x, decimals_y
        )
        upper_price = MeteoraMath.get_price_from_id(
            upper_id, bin_step, decimals_x, decimals_y
        )
        
        return (lower_price, upper_price)
    
    @staticmethod
    def get_price_offset(
        base_price: float,
        offset_bps: int,
        bin_step: int,
    ) -> float:
        """
        Calculate price after moving a certain number of bins.
        
        Args:
            base_price: Base price
            offset_bps: Offset in basis points of bin step
            bin_step: Bin step
            
        Returns:
            New price
        """
        # Each bin move multiplies/divides by (1 + bin_step/10000)
        factor = (Decimal(1) + Decimal(bin_step) / Decimal(10000)) ** Decimal(offset_bps)
        new_price = Decimal(base_price) * factor
        
        return float(new_price)
    
    @staticmethod
    def estimate_liquidity_depth(
        bin_step: int,
        active_id: int,
        total_liquidity: int,
    ) -> float:
        """
        Estimate liquidity depth at current bin.
        
        Args:
            bin_step: Bin step
            active_id: Current active bin
            total_liquidity: Total liquidity in pool
            
        Returns:
            Estimated depth factor
        """
        # Simplified: liquidity is distributed across bins
        # Higher bin_step = wider distribution = less depth per bin
        base = Decimal(1) + Decimal(bin_step) / Decimal(10000)
        depth_factor = Decimal(total_liquidity) / (base ** Decimal(abs(active_id - BIN_ID_OFFSET)))
        
        return float(depth_factor)


# Convenience functions (pure wrappers)
def get_price_from_id(
    active_id: int,
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> float:
    """
    Convert bin ID to real price.
    
    Args:
        active_id: Active bin ID
        bin_step: Bin step
        decimals_x: Decimals of token X
        decimals_y: Decimals of token Y
        
    Returns:
        Price of X in terms of Y
    """
    return MeteoraMath.get_price_from_id(
        active_id, bin_step, decimals_x, decimals_y
    )


def get_id_from_price(
    price: float,
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> int:
    """
    Convert real price to bin ID.
    
    Args:
        price: Price
        bin_step: Bin step
        decimals_x: Decimals of token X
        decimals_y: Decimals of token Y
        
    Returns:
        Bin ID
    """
    return MeteoraMath.get_id_from_price(
        price, bin_step, decimals_x, decimals_y
    )


def get_bin_range_price(
    lower_id: int,
    upper_id: int,
    bin_step: int,
    decimals_x: int,
    decimals_y: int,
) -> Tuple[float, float]:
    """
    Get price range for bin interval.
    
    Args:
        lower_id: Lower bin ID
        upper_id: Upper bin ID
        bin_step: Bin step
        decimals_x: Decimals of token X
        decimals_y: Decimals of token Y
        
    Returns:
        Tuple of (lower_price, upper_price)
    """
    return MeteoraMath.get_bin_range_price(
        lower_id, upper_id, bin_step, decimals_x, decimals_y
    )
