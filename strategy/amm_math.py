"""
AMM Constant Product Math (Uniswap v2 style)

Pure functions for calculating swap amounts and price impact.
No external dependencies, no I/O.
"""

from typing import Tuple


def get_amount_out(
    amount_in: float,
    reserve_in: float,
    reserve_out: float,
    fee_bps: int = 30
) -> float:
    """
    Calculate output amount for a swap using constant product formula.
    
    Formula: amount_out = (amount_in * (1 - fee) * reserve_out) / (reserve_in + amount_in * (1 - fee))
    
    Args:
        amount_in: Amount of input token being sold
        reserve_in: Reserve of input token in the pool
        reserve_out: Reserve of output token in the pool
        fee_bps: Fee in basis points (default 30 = 0.3%)
    
    Returns:
        Amount of output token received
    
    Raises:
        ValueError: If reserves are zero or negative
        ValueError: If amount_in is negative
    """
    # Validation
    if amount_in < 0:
        raise ValueError("amount_in must be non-negative")
    
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("Reserves must be positive")
    
    # Tiny amounts return 0 (no meaningful trade)
    if amount_in == 0:
        return 0.0
    
    # Calculate fee factor (1 - fee)
    fee_factor = 1.0 - (fee_bps / 10000.0)
    
    # Amount in after fee
    amount_in_after_fee = amount_in * fee_factor
    
    # Constant product formula
    numerator = amount_in_after_fee * reserve_out
    denominator = reserve_in + amount_in_after_fee
    
    amount_out = numerator / denominator
    
    # Sanity check: can't get more than available
    return min(amount_out, reserve_out)


def get_price_impact_bps(
    amount_in: float,
    reserve_in: float,
    reserve_out: float,
    fee_bps: int = 30
) -> float:
    """
    Calculate price impact in basis points.
    
    Impact measures how much the execution price deviates from the mid price
    due to the AMM curve (not including fees).
    
    Mid price = reserve_out / reserve_in
    
    Args:
        amount_in: Amount of input token being sold
        reserve_in: Reserve of input token in the pool
        reserve_out: Reserve of output token in the pool
        fee_bps: Fee in basis points (used for actual output calculation)
    
    Returns:
        Price impact in basis points (positive = adverse impact)
    """
    # Validation
    if amount_in < 0:
        raise ValueError("amount_in must be non-negative")
    
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("Reserves must be positive")
    
    if amount_in == 0:
        return 0.0
    
    # Mid price (spot price before trade)
    mid_price = reserve_out / reserve_in
    
    # Ideal output without any curve impact (just mid price)
    ideal_out = amount_in * mid_price
    
    # Actual output with curve impact (but no fees for pure impact measure)
    # Impact is purely from the curve distortion
    actual_out_no_fee = get_amount_out(amount_in, reserve_in, reserve_out, fee_bps=0)
    
    # Calculate impact: (ideal - actual) / ideal
    if ideal_out <= 0:
        return 0.0
    
    impact_ratio = (ideal_out - actual_out_no_fee) / ideal_out
    
    # Convert to basis points
    impact_bps = impact_ratio * 10000.0
    
    return impact_bps


def get_execution_price(
    amount_in: float,
    reserve_in: float,
    reserve_out: float,
    fee_bps: int = 30
) -> float:
    """
    Calculate the actual execution price (output per unit input).
    
    Args:
        amount_in: Amount of input token being sold
        reserve_in: Reserve of input token in the pool
        reserve_out: Reserve of output token in the pool
        fee_bps: Fee in basis points
    
    Returns:
        Execution price (output tokens per input token)
    """
    amount_out = get_amount_out(amount_in, reserve_in, reserve_out, fee_bps)
    
    if amount_in <= 0:
        return 0.0
    
    return amount_out / amount_in


def estimate_slippage_bps(
    pool_address: str,
    amount_in: int,
    token_mint: str,
    reserve_in: float,
    reserve_out: float,
    fee_bps: int = 25,
) -> int:
    """
    Estimate expected slippage in basis points for a given purchase size.
    
    Uses XYK constant product formula: x * y = k
    
    Formula: Δy = y - (x*y) / (x + Δx)
    
    Args:
        pool_address: Address of the AMM pool
        amount_in: Amount of input token being purchased (raw units)
        token_mint: Mint address of input token
        reserve_in: Reserve of input token in pool (raw units)
        reserve_out: Reserve of output token in pool (raw units)
        fee_bps: Fee tier in basis points (default 25 = 0.25%)
        
    Returns:
        Estimated slippage in basis points (int, rounded)
        
    Raises:
        ValueError: If amount_in <= 0 or reserves are invalid
    """
    # Validation
    if amount_in <= 0:
        raise ValueError("amount_in must be positive")
    
    if reserve_in <= 0 or reserve_out <= 0:
        raise ValueError("Reserves must be positive")
    
    # Convert to float for calculation
    amount = float(amount_in)
    
    # If amount is negligible compared to reserve, slippage is near zero
    if amount < reserve_in * 0.0001:  # < 0.01% of reserve
        return 0
    
    # Calculate output with fees (actual swap)
    fee_factor = 1.0 - (fee_bps / 10000.0)
    amount_after_fee = amount * fee_factor
    
    # Constant product: new_reserve_out = (reserve_in * reserve_out) / (reserve_in + amount_in_after_fee)
    # Output = reserve_out - new_reserve_out
    numerator = reserve_in * reserve_out
    denominator = reserve_in + amount_after_fee
    new_reserve_out = numerator / denominator
    actual_output = reserve_out - new_reserve_out
    
    # Mid price (no slippage, no fees)
    # 1 unit of input = reserve_out / reserve_out of output
    ideal_output = amount * (reserve_out / reserve_in)
    
    # Slippage ratio: (ideal - actual) / ideal
    # This captures both curve impact AND fees
    if ideal_output <= 0:
        return 0
    
    slippage_ratio = (ideal_output - actual_output) / ideal_output
    
    # Convert to basis points
    slippage_bps = round(slippage_ratio * 10000.0)
    
    # Clamp to valid range
    return max(0, min(slippage_bps, 10000))


def estimate_whirlpool_slippage_bps(
    liquidity: int,
    sqrt_price_x64: int,
    tick_spacing: int,
    size_usd: float,
    token_price_usd: float,
    sol_price_usd: float = 100.0,
) -> int:
    """
    Simplified slippage estimation for Orca Whirlpools concentrated liquidity.
    
    Model: effective_liquidity ≈ liquidity * sqrt_price * tick_spacing_factor
    
    In Orca Whirlpools:
    - liquidity is stored as u128 (actual L value, not sqrt(L))
    - sqrt_price_x64 is stored as Q64.64 fixed-point
    
    Formula:
    effective_liquidity_usd = liquidity * (sqrt_price_x64 / 2^64) * sol_price_usd * tick_spacing_factor
    
    Args:
        liquidity: Current pool liquidity (u128 integer from on-chain data)
        sqrt_price_x64: Square root of price as Q64.64 integer
        tick_spacing: Tick spacing for the pool (e.g., 64 for standard pools)
        size_usd: Purchase size in USD
        token_price_usd: Current token price in USD (unused but kept for API compatibility)
        sol_price_usd: SOL price in USD (default 100.0)
        
    Returns:
        Estimated slippage in basis points (0-10000, capped)
    """
    # Handle edge cases
    if liquidity <= 0 or sqrt_price_x64 <= 0:
        return 9999  # extreme slippage for empty pools
    
    # Convert sqrt_price_x64 from Q64.64 to normal floating point
    # Q64.64 means: value = raw / 2^64
    sqrt_price_normalized = sqrt_price_x64 / (2 ** 64)
    
    if sqrt_price_normalized <= 0:
        return 9999
    
    # tick_spacing_factor: wider ticks = less concentrated = more slippage
    # Standard tick spacing is 64, normalize to this baseline
    tick_spacing_factor = max(1.0, tick_spacing / 64.0)
    
    # Effective liquidity in SOL terms:
    # liquidity is the actual L value (not sqrt(L) like in Uniswap V3)
    # For a concentrated pool, the effective depth at current price is:
    # L * sqrt(P) where P = (sqrt_price)^2
    # So: L * sqrt_price gives us SOL equivalent depth at current tick
    
    # Apply Q64.64 scaling to sqrt_price
    effective_liquidity_sol = liquidity * sqrt_price_normalized * tick_spacing_factor
    
    # Convert to USD
    effective_liquidity_usd = effective_liquidity_sol * sol_price_usd
    
    if effective_liquidity_usd <= 0:
        return 9999
    
    # Size ratio as fraction of effective liquidity
    size_ratio = size_usd / effective_liquidity_usd
    
    # Linear slippage model: slippage ≈ size_ratio
    # Convert to percentage: slippage_pct = size_ratio * 100
    
    # Non-linear correction for large swaps (>10% of effective liquidity)
    # Large trades impact more than proportionally due to tick boundaries
    if size_ratio > 0.1:
        slippage_pct = size_ratio * 100.0 * (1.0 + 0.5 * (size_ratio - 0.1) / 0.9)
    else:
        slippage_pct = size_ratio * 100.0
    
    # Convert to basis points with bounds (1% = 100 bps)
    slippage_bps = max(0, min(10000, int(round(slippage_pct * 100))))
    return slippage_bps


class ConstantProduct:
    """
    Wrapper class for constant product pool state.
    """
    
    def __init__(self, reserve_in: float, reserve_out: float, fee_bps: int = 30):
        """
        Initialize a constant product pool.
        
        Args:
            reserve_in: Reserve of input token
            reserve_out: Reserve of output token
            fee_bps: Swap fee in basis points
        """
        if reserve_in <= 0 or reserve_out <= 0:
            raise ValueError("Reserves must be positive")
        
        self.reserve_in = reserve_in
        self.reserve_out = reserve_out
        self.fee_bps = fee_bps
        self.k = reserve_in * reserve_out
    
    def get_amount_out(self, amount_in: float) -> float:
        """Calculate output for a given input amount."""
        return get_amount_out(amount_in, self.reserve_in, self.reserve_out, self.fee_bps)
    
    def get_price_impact_bps(self, amount_in: float) -> float:
        """Calculate price impact for a given input amount."""
        return get_price_impact_bps(amount_in, self.reserve_in, self.reserve_out, self.fee_bps)
    
    def get_execution_price(self, amount_in: float) -> float:
        """Calculate execution price for a given input amount."""
        return get_execution_price(amount_in, self.reserve_in, self.reserve_out, self.fee_bps)
    
    def simulate_swap(self, amount_in: float) -> Tuple[float, float, float, float]:
        """
        Simulate a complete swap and return all metrics.
        
        Returns:
            Tuple of (amount_out, impact_bps, execution_price, mid_price)
        """
        amount_out = self.get_amount_out(amount_in)
        impact_bps = self.get_price_impact_bps(amount_in)
        execution_price = get_execution_price(amount_in, self.reserve_in, self.reserve_out, self.fee_bps)
        mid_price = self.reserve_out / self.reserve_in
        
        return amount_out, impact_bps, execution_price, mid_price


# PR-MET.1: Meteora DLMM Slippage Estimation

def estimate_dlmm_slippage_bps(
    active_bin_liquidity: int,  # суммарная ликвидность в активных бинах (±3 от текущего)
    bin_step_bps: int,          # размер шага бина в базисных пунктах (1 = 0.01%)
    size_usd: float,            # размер покупки в USD
    token_price_usd: float,     # текущая цена токена в USD
    sol_price_usd: float = 100.0
) -> int:
    """
    Упрощённая оценка slippage для бин-базированной ликвидности Meteora DLMM.
    
    Модель: эффективная глубина ~ активная ликвидность * плотность бинов
    
    В Meteora DLMM:
    - Ликвидность распределена по дискретным ценовым интервалам (бинам)
    - Каждый bin имеет фиксированный размер (bin_step_bps)
    - Активная ликвидность — сумма ликвидности в ±3 бинах от текущей цены
    
    Формула:
    1. bin_density_factor = min(5.0, 100.0 / bin_step_bps)
       — чем мельче шаг бина, тем выше концентрация ликвидности
    
    2. effective_depth_usd = (active_bin_liquidity / 1e6) * token_price_usd * bin_density_factor
       — нормализуем "квоты" в реальную глубину
    
    3. size_ratio = size_usd / effective_depth_usd
    
    4. non-linear correction при size_ratio > 0.15:
       slippage_pct = size_ratio * 100 * (1 + 0.7 * (size_ratio - 0.15) / 0.85)
    
    Args:
        active_bin_liquidity: Суммарная ликвидность в активных бинах (целое число)
        bin_step_bps: Размер шага бина в базисних пунктах (1-10000)
        size_usd: Размер покупки в USD
        token_price_usd: Текущая цена токена в USD
        sol_price_usd: Цена SOL в USD (по умолчанию 100.0)
        
    Returns:
        Estimated slippage в basis points (0-10000, capped)
    """
    # Edge cases
    if active_bin_liquidity <= 0 or bin_step_bps <= 0:
        return 9999  # extreme slippage для пустых пулов
    
    if size_usd <= 0:
        return 0
    
    # Плотность ликвидности: чем мельче шаг бина, тем выше концентрация
    # Базовый нормализатор: 100 bps = 1% шаг → плотность 1.0
    bin_density_factor = min(5.0, 100.0 / max(1, bin_step_bps))
    
    # Эффективная глубина в USD
    # Активная ликвидность измеряется в "квотах" — нормализуем к реальным токенам
    # Делим на 1e6 как упрощённый нормализатор
    effective_token_amount = active_bin_liquidity / 1e6
    effective_depth_usd = effective_token_amount * token_price_usd * bin_density_factor
    
    # Минимальная глубина для расчёта
    if effective_depth_usd <= 100.0:
        return 9999
    
    # Базовый расчёт как доля от эффективной глубины
    size_ratio = size_usd / effective_depth_usd
    
    # Нелинейная коррекция для крупных свопов (>15% глубины)
    if size_ratio > 0.15:
        slippage_pct = size_ratio * 100.0 * (1.0 + 0.7 * (size_ratio - 0.15) / 0.85)
    else:
        slippage_pct = size_ratio * 100.0
    
    # Конвертация в basis points с ограничением
    slippage_bps = max(0, min(10000, int(round(slippage_pct * 100))))
    
    return slippage_bps
