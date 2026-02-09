"""
strategy/analytics/clustering.py

Wallet clustering using K-Means with semantic labels.

PR-V.1
"""
import sys
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from strategy.analytics.wallet_features import extract_features, normalize_features


# Feature column names (must match wallet_features.py)
FEATURE_COLS = [
    'med_entry_delay_log',
    'winrate',
    'avg_hold_sec_log',
    'profit_factor',
    'tx_count_log',
]


class WalletClusterer:
    """
    ML-based wallet clustering for behavioral archetypes.
    
    Uses K-Means with semantic label assignment based on centroid characteristics.
    
    PR-V.1
    """
    
    # Semantic labels for clusters
    LABELS = {
        'SNIPER': 'Smart Sniper',
        'LEADER': 'Smart Holder (Leader)',
        'FOLLOWER': 'Follower',
        'NOISE': 'Noise',
        'LOSER': 'Consistent Loser',
    }
    
    def __init__(self, n_clusters: int = 5, random_state: int = 42):
        """
        Initialize the clusterer.
        
        Args:
            n_clusters: Number of clusters (default 5 for behavioral archetypes)
            random_state: Random seed for reproducibility
        """
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,  # Deterministic clustering
            n_init=10,
            max_iter=300,
        )
        self.cluster_labels_: Optional[Dict[int, str]] = None
        self.centroids_: Optional[np.ndarray] = None
        self._is_fitted = False
    
    def fit(self, trades_df: pd.DataFrame) -> 'WalletClusterer':
        """
        Fit the clustering model on trade history.
        
        Args:
            trades_df: DataFrame with trade history
            
        Returns:
            self for chaining
        """
        # Extract features
        features_df = extract_features(trades_df)
        
        if len(features_df) == 0:
            raise ValueError("No features to cluster - empty input data")
        
        # Normalize
        scaled_features, self.scaler = normalize_features(features_df)
        
        # Fit K-Means
        self.kmeans.fit(scaled_features)
        self.centroids_ = self.kmeans.cluster_centers_
        
        # Assign semantic labels to clusters
        self.cluster_labels_ = self._assign_labels(self.centroids_)
        
        self._is_fitted = True
        
        print(f"[clustering] K-Means fitted with {self.n_clusters} clusters", file=sys.stderr)
        
        return self
    
    def fit_predict(self, trades_df: pd.DataFrame) -> pd.Series:
        """
        Fit and return cluster assignments.
        
        Args:
            trades_df: DataFrame with trade history
            
        Returns:
            Series with wallet as index and cluster label as value
        """
        self.fit(trades_df)
        return self.predict(trades_df)
    
    def predict(self, trades_df: pd.DataFrame) -> pd.Series:
        """
        Predict cluster assignments for wallets in new data.
        
        Args:
            trades_df: DataFrame with trade history
            
        Returns:
            Series with wallet as index and cluster label as value
        """
        if not self._is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")
        
        # Extract features
        features_df = extract_features(trades_df)
        
        if len(features_df) == 0:
            return pd.Series(dtype=str)
        
        # Normalize using fitted scaler
        scaled_features, _ = normalize_features(features_df, self.scaler)
        
        # Predict clusters
        cluster_ids = self.kmeans.predict(scaled_features)
        
        # Map to semantic labels
        labels = [self.cluster_labels_[cid] for cid in cluster_ids]
        
        return pd.Series(labels, index=features_df.index)
    
    def _assign_labels(self, centroids: np.ndarray) -> Dict[int, str]:
        """
        Assign semantic labels to clusters based on centroid characteristics.
        
        Heuristics:
        - High winrate + Low delay = Smart Sniper
        - High winrate + Med delay + High hold = Smart Holder (Leader)
        - High winrate + High delay = Follower
        - Low winrate = Noise/Loser
        
        Args:
            centroids: Cluster centroids in normalized feature space
            
        Returns:
            Dictionary mapping cluster_id -> semantic_label
        """
        labels = {}
        
        # Feature indices in centroid array
        IDX_DELAY = 0      # med_entry_delay_log
        IDX_WINRATE = 1    # winrate
        IDX_HOLD = 2       # avg_hold_sec_log
        IDX_PROFIT = 3     # profit_factor
        IDX_TX = 4         # tx_count_log
        
        for cid in range(len(centroids)):
            centroid = centroids[cid]
            
            # Extract characteristics (remember: these are normalized)
            delay = centroid[IDX_DELAY]
            winrate = centroid[IDX_WINRATE]
            hold = centroid[IDX_HOLD]
            profit = centroid[IDX_PROFIT]
            
            # Apply heuristics (using normalized thresholds)
            # Lower delay = higher normalized value (since we use log)
            # Actually: higher delay = higher log value
            # So: LOW delay = lower centroid value
            
            high_winrate = winrate > 0.0
            low_delay = delay < 0.0
            high_hold = hold > 0.0
            high_profit = profit > 0.0
            
            # Classification logic
            if high_winrate and low_delay and high_profit:
                label = self.LABELS['SNIPER']
            elif high_winrate and high_hold and high_profit:
                label = self.LABELS['LEADER']
            elif high_winrate and not low_delay:
                label = self.LABELS['FOLLOWER']
            elif not high_winrate and profit < -0.5:
                label = self.LABELS['LOSER']
            else:
                label = self.LABELS['NOISE']
            
            labels[cid] = label
        
        return labels
    
    def get_cluster_stats(self, trades_df: pd.DataFrame) -> Dict[str, dict]:
        """
        Get statistics for each cluster.
        
        Args:
            trades_df: DataFrame with trade history
            
        Returns:
            Dictionary mapping label -> statistics dict
        """
        if not self._is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")
        
        # Get cluster assignments
        labels = self.fit_predict(trades_df)
        
        # Get features for statistics
        features_df = extract_features(trades_df)
        
        stats = {}
        for label in set(labels):
            wallets = labels[labels == label].index
            cluster_features = features_df.loc[wallets]
            
            stats[label] = {
                'count': len(wallets),
                'avg_winrate': cluster_features['winrate'].mean(),
                'avg_delay': np.exp(cluster_features['med_entry_delay_log'].mean()),
                'avg_hold': np.exp(cluster_features['avg_hold_sec_log'].mean()),
            }
        
        return stats
    
    def get_centroids(self) -> pd.DataFrame:
        """
        Get cluster centroids as a DataFrame.
        
        Returns:
            DataFrame with cluster labels as index and features as columns
        """
        if self.centroids_ is None:
            raise ValueError("Model not fitted. Call fit() first.")
        
        centroids_df = pd.DataFrame(
            self.centroids_,
            columns=FEATURE_COLS,
            index=[self.cluster_labels_[i] for i in range(len(self.centroids_))]
        )
        
        return centroids_df
