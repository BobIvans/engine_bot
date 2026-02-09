"""
strategy/analytics/wallet_features.py

Feature engineering for wallet clustering.

Transforms raw trade history into behavioral feature vectors.

PR-V.1
"""
import sys
from typing import Dict, List, Optional
import pandas as pd
import numpy as np


def log_transform(x: float, eps: float = 1e-6) -> float:
    """Apply log transform with epsilon to avoid log(0)."""
    return np.log(max(x, eps))


def extract_features(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract behavioral features for each wallet.
    
    Input columns: wallet, token, entry_time, pool_open_time, pnl_pct, hold_seconds
    
    Output features per wallet:
    - med_entry_delay_log: log of median entry delay (seconds)
    - winrate: fraction of trades with pnl_pct > 0
    - avg_hold_sec: average hold time in seconds
    - profit_factor: gross profit / gross loss (min 0.01)
    - tx_count_log: log of transaction count
    
    Args:
        trades_df: DataFrame with trade history
        
    Returns:
        DataFrame with wallet as index and feature columns
        
    Raises:
        ValueError: If required columns are missing
    """
    required_cols = ['wallet', 'token', 'entry_time', 'pool_open_time', 'pnl_pct', 'hold_seconds']
    missing = [c for c in required_cols if c not in trades_df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Calculate entry delay for each trade
    # entry_time and pool_open_time are timestamps or seconds
    trades_df = trades_df.copy()
    
    # If entry_time and pool_open_time are numeric (seconds), calculate delay
    # If they're timestamps, convert to datetime first
    if trades_df['entry_time'].dtype in ['int64', 'float64']:
        trades_df['entry_delay'] = trades_df['entry_time'] - trades_df['pool_open_time']
    else:
        # Assume they're datetime strings or timestamps
        try:
            trades_df['entry_dt'] = pd.to_datetime(trades_df['entry_time'])
            trades_df['pool_dt'] = pd.to_datetime(trades_df['pool_open_time'])
            trades_df['entry_delay'] = (trades_df['entry_dt'] - trades_df['pool_dt']).dt.total_seconds()
        except Exception:
            # Fallback: assume numeric delay already
            trades_df['entry_delay'] = 0
    
    # Ensure entry_delay is non-negative
    trades_df['entry_delay'] = trades_df['entry_delay'].clip(lower=0)
    
    # Group by wallet and calculate features
    features = []
    
    for wallet, group in trades_df.groupby('wallet'):
        if len(group) == 0:
            continue
        
        # Entry delay (log of median)
        med_delay = group['entry_delay'].median()
        med_entry_delay_log = log_transform(med_delay)
        
        # Winrate
        winrate = (group['pnl_pct'] > 0).mean()
        
        # Average hold time (log)
        avg_hold_sec = group['hold_seconds'].mean()
        avg_hold_sec_log = log_transform(avg_hold_sec)
        
        # Profit factor: gross profit / gross loss
        profits = group[group['pnl_pct'] > 0]['pnl_pct'].sum()
        losses = abs(group[group['pnl_pct'] < 0]['pnl_pct'].sum())
        profit_factor = max(profits / max(losses, 0.01), 0.01)  # Avoid division by zero
        
        # TX count (log)
        tx_count = len(group)
        tx_count_log = log_transform(tx_count)
        
        features.append({
            'wallet': wallet,
            'med_entry_delay_log': med_entry_delay_log,
            'winrate': winrate,
            'avg_hold_sec_log': avg_hold_sec_log,
            'profit_factor': np.log(profit_factor + 1),  # log-transform profit factor
            'tx_count_log': tx_count_log,
        })
    
    if not features:
        print("[wallet_features] WARNING: No features extracted (empty input)", file=sys.stderr)
        return pd.DataFrame(columns=['wallet', 'med_entry_delay_log', 'winrate', 
                                     'avg_hold_sec_log', 'profit_factor', 'tx_count_log'])
    
    result_df = pd.DataFrame(features)
    result_df.set_index('wallet', inplace=True)
    
    print(f"[wallet_features] Features extracted: {result_df.shape} (OK)", file=sys.stderr)
    
    return result_df


def normalize_features(features_df: pd.DataFrame, scaler=None) -> tuple:
    """
    Normalize features using StandardScaler.
    
    Args:
        features_df: DataFrame with feature columns
        scaler: Optional pre-fitted StandardScaler
        
    Returns:
        Tuple of (scaled_array, scaler)
    """
    from sklearn.preprocessing import StandardScaler
    
    if scaler is None:
        scaler = StandardScaler()
        scaled = scaler.fit_transform(features_df.values)
    else:
        scaled = scaler.transform(features_df.values)
    
    return scaled, scaler
