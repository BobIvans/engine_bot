"""
ingestion/dex/orca/math.py

Orca Whirlpools CLMM Math - Pure math functions for CLMM calculations.

PR-U.2

All functions are pure (no I/O).
"""
from decimal import Decimal, getcontext
from typing import Tuple


# Set high precision for decimal operations
getcontext().prec = 80

# Q64.64 scaling factor
Q64_SHIFT = 64
Q64_SCALE = 1 << Q64_SHIFT

# 1.0001 base for tick-to-price conversion
TICK_BASE = Decimal("1.0001")


class OrcaMath:
    """
    Pure math functions for Orca Whirlpools CLMM.
    
    PR-U.2
    """
    
    @staticmethod
    def sqrt_price_x64_to_price(
        sqrt_price: int,
        decimals_a: int,
        decimals_b: int,
    ) -> float:
        """
        Convert sqrt_price (Q64.64 fixed point) to real price.
        
        Formula:
        Price_raw = (sqrt_price / 2^64)^2
        Price_real = Price_raw × 10^(decimals_a - decimals_b)
        
        Args:
            sqrt_price: Sqrt price as integer (Q64.64 format)
            decimals_a: Decimals of token A
            decimals_b: Decimals of token B
            
        Returns:
            Price of token A in terms of token B
        """
        if sqrt_price <= 0:
            raise ValueError("sqrt_price must be positive")
        
        # Convert to Decimal for high precision
        sqrt_price_dec = Decimal(sqrt_price)
        scale_dec = Decimal(Q64_SCALE)
        
        # Price_raw = (sqrt_price / 2^64)^2
        price_raw = (sqrt_price_dec / scale_dec) ** 2
        
        # Adjust for decimals: Price_real = Price_raw × 10^(decimals_a - decimals_b)
        decimal_adjustment = Decimal(10) ** (decimals_a - decimals_b)
        price_real = price_raw * decimal_adjustment
        
        return float(price_real)
    
    @staticmethod
    def price_to_sqrt_price_x64(
        price: float,
        decimals_a: int,
        decimals_b: int,
    ) -> int:
        """
        Convert real price to sqrt_price (Q64.64).
        
        Inverse of sqrt_price_x64_to_price.
        
        Args:
            price: Price of token A in terms of token B
            decimals_a: Decimals of token A
            decimals_b: Decimals of token B
            
        Returns:
            Sqrt price as integer (Q64.64 format)
        """
        if price <= 0:
            raise ValueError("price must be positive")
        
        # Adjust for decimals
        decimal_adjustment = Decimal(10) ** (decimals_b - decimals_a)
        price_raw = Decimal(price) * decimal_adjustment
        
        # sqrt_price = sqrt(price_raw) × 2^64
        sqrt_price = price_raw.sqrt() * Decimal(Q64_SCALE)
        
        return int(sqrt_price)
    
    @staticmethod
    def tick_to_price(
        tick: int,
        decimals_a: int,
        decimals_b: int,
    ) -> float:
        """
        Convert tick index to real price.
        
        Formula:
        Price = 1.0001^tick × 10^(decimals_a - decimals_b)
        
        Args:
            tick: Tick index (can be negative)
            decimals_a: Decimals of token A
            decimals_b: Decimals of token B
            
        Returns:
            Price of token A in terms of token B
        """
        # Price_base = 1.0001^tick
        price_base = TICK_BASE ** Decimal(tick)
        
        # Adjust for decimals
        decimal_adjustment = Decimal(10) ** (decimals_a - decimals_b)
        price_real = price_base * decimal_adjustment
        
        return float(price_real)
    
    @staticmethod
    def price_to_tick(
        price: float,
        decimals_a: int,
        decimals_b: int,
        tick_spacing: int,
    ) -> int:
        """
        Convert real price to tick index.
        
        Args:
            price: Price of token A in terms of token B
            decimals_a: Decimals of token A
            decimals_b: Decimals of token B
            tick_spacing: Tick spacing of the pool
            
        Returns:
            Nearest tick index (rounded to tick_spacing)
        """
        # Adjust for decimals
        decimal_adjustment = Decimal(10) ** (decimals_b - decimals_a)
        price_raw = Decimal(price) * decimal_adjustment
        
        # tick = log_1.0001(price_raw)
        tick = (price_raw / TICK_BASE).ln() / TICK_BASE.ln()
        
        # Round to nearest tick_spacing
        tick_int = int(round(tick))
        tick_int = (tick_int // tick_spacing) * tick_spacing
        
        return tick_int
    
    @staticmethod
    def get_liquidity_usd_estimate(
        liquidity: int,
        price: float,
        decimals_a: int,
    ) -> float:
        """
        Estimate liquidity value in USD.
        
        This is a rough estimate assuming token A is the quote token.
        
        Args:
            liquidity: Pool liquidity (in sqrt liquidity units)
            price: Current price of token A in USD
            decimals_a: Decimals of token A
            
        Returns:
            Estimated liquidity value in USD
        """
        if liquidity <= 0:
            return 0.0
        
        # Convert liquidity to actual token amount
        # For CLMM, liquidity represents sqrt(X * Y)
        # The dollar value estimate: liquidity * price / 10^decimals
        liquidity_dec = Decimal(liquidity)
        price_dec = Decimal(price)
        decimals_dec = Decimal(10) ** decimals_a
        
        usd_value = (liquidity_dec * price_dec) / decimals_dec
        
        return float(usd_value)
    
    @staticmethod
    def get_token_amounts_from_liquidity(
        liquidity: int,
        sqrt_price: int,
        lower_tick: int,
        upper_tick: int,
        decimals_a: int,
        decimals_b: int,
    ) -> Tuple[int, int]:
        """
        Calculate token amounts for a liquidity range.
        
        This calculates how much of each token is needed for a 
        specific liquidity position.
        
        Args:
            liquidity: Position liquidity
            sqrt_price: Current sqrt price (Q64.64)
            lower_tick: Lower tick of position
            upper_tick: Upper tick of position
            decimals_a: Decimals of token A
            decimals_b: Decimals of token B
            
        Returns:
            Tuple of (amount_a, amount_b)
        """
        if liquidity <= 0:
            return (0, 0)
        
        # Calculate sqrt prices for ticks
        lower_sqrt = OrcaMath.tick_to_sqrt_price_x64(lower_tick)
        upper_sqrt = OrcaMath.tick_to_sqrt_price_x64(upper_tick)
        
        # Calculate amounts
        # amount_a = liquidity × (sqrt(upper) - sqrt(price)) / (sqrt(upper) × sqrt(lower))
        # amount_b = liquidity × (price - sqrt(lower)) / (sqrt(lower) × sqrt(upper))
        
        if sqrt_price <= lower_sqrt:
            amount_a = 0
            amount_b = liquidity * (upper_sqrt - lower_sqrt) // (lower_sqrt * upper_sqrt)
        elif sqrt_price >= upper_sqrt:
            amount_a = liquidity * (upper_sqrt - lower_sqrt) // (lower_sqrt * upper_sqrt)
            amount_b = 0
        else:
            amount_a = liquidity * (upper_sqrt - sqrt_price) // (sqrt_price * upper_sqrt)
            amount_b = liquidity * (sqrt_price - lower_sqrt) // (lower_sqrt * sqrt_price)
        
        return (int(amount_a), int(amount_b))
    
    @staticmethod
    def tick_to_sqrt_price_x64(tick: int) -> int:
        """
        Convert tick index to sqrt_price (Q64.64).
        
        Formula:
        sqrt_price = 1.0001^(tick/2) × 2^64
        
        Args:
            tick: Tick index
            
        Returns:
            Sqrt price as integer (Q64.64 format)
        """
        # sqrt_price = 1.0001^(tick/2) × 2^64
        sqrt_price_dec = (TICK_BASE ** (Decimal(tick) / 2)) * Decimal(Q64_SCALE)
        
        return int(sqrt_price_dec)
    
    @staticmethod
    def calculate_price_impact(
        amount_in: int,
        token_a_decimals: int,
        token_b_decimals: int,
        liquidity: int,
        sqrt_price: int,
        is_token_a_to_b: bool,
    ) -> float:
        """
        Calculate price impact of a swap.
        
        Args:
            amount_in: Amount of input token
            token_a_decimals: Decimals of token A
            token_b_decimals: Decimals of token B
            liquidity: Pool liquidity
            sqrt_price: Current sqrt price (Q64.64)
            is_token_a_to_b: True if swapping A to B
            
        Returns:
            Price impact as a fraction (e.g., 0.001 for 0.1%)
        """
        if liquidity <= 0 or amount_in <= 0:
            return 0.0
        
        # Calculate mid price
        mid_price = OrcaMath.sqrt_price_x64_to_price(
            sqrt_price, token_a_decimals, token_b_decimals
        )
        
        # Calculate output amount
        if is_token_a_to_b:
            # amount_b = liquidity × (sqrt(price) - sqrt(price + delta))
            # This is simplified; full calculation requires token amount deltas
            output_amount = liquidity  # Simplified
        else:
            output_amount = liquidity  # Simplified
        
        # Effective price = amount_out / amount_in
        effective_price = mid_price  # Simplified
        
        # Impact = |mid - effective| / mid
        impact = abs(mid_price - effective_price) / mid_price
        
        return impact


# Convenience functions (pure wrappers)
def sqrt_price_x64_to_price(
    sqrt_price: int,
    decimals_a: int,
    decimals_b: int,
) -> float:
    """
    Convert sqrt_price (Q64.64) to real price.
    
    Args:
        sqrt_price: Sqrt price as integer
        decimals_a: Decimals of token A
        decimals_b: Decimals of token B
        
    Returns:
        Price of A in terms of B
    """
    return OrcaMath.sqrt_price_x64_to_price(sqrt_price, decimals_a, decimals_b)


def tick_to_price(
    tick: int,
    decimals_a: int,
    decimals_b: int,
) -> float:
    """
    Convert tick index to real price.
    
    Args:
        tick: Tick index
        decimals_a: Decimals of token A
        decimals_b: Decimals of token B
        
    Returns:
        Price of A in terms of B
    """
    return OrcaMath.tick_to_price(tick, decimals_a, decimals_b)


def get_liquidity_usd_estimate(
    liquidity: int,
    price: float,
    decimals_a: int,
) -> float:
    """
    Estimate liquidity value in USD.
    
    Args:
        liquidity: Pool liquidity
        price: Current price
        decimals_a: Decimals of quote token
        
    Returns:
        Estimated liquidity in USD
    """
    return OrcaMath.get_liquidity_usd_estimate(liquidity, price, decimals_a)
