"""analysis/token_mapping.py

PR-PM.4: Polymarket → Solana Token Mapping

Pure functions for semantic mapping of Polymarket markets to Solana memecoins
via three strategies:
1. exact_symbol - exact token symbol match ($TRUMP in question)
2. thematic - theme-based matching (politics → $TRUMP/$HARRIS)
3. fuzzy_name - normalized word match from token name

All functions are deterministic and side-effect free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set


# =============================================================================
# Data Classes
# =============================================================================

@dataclass(frozen=True)
class PolymarketSnapshot:
    """Polymarket market snapshot for token mapping."""
    id: str
    question: str
    # Optional fields for future extension
    category: Optional[str] = None
    end_date_unix_ms: Optional[int] = None


@dataclass(frozen=True)
class TokenSnapshot:
    """Solana token snapshot for mapping."""
    mint: str
    symbol: str
    name: str
    # Optional fields
    liquidity_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None


@dataclass(frozen=True)
class MappingResult:
    """Result of a single token mapping."""
    market_id: str
    token_mint: str
    token_symbol: str
    relevance_score: float  # [0.6, 1.0]
    mapping_type: str  # "exact_symbol", "thematic", "fuzzy_name"
    matched_keywords: List[str]


# =============================================================================
# Constants
# =============================================================================

# Theme keywords for thematic matching
THEMES = {
    "politics": ["trump", "harris", "biden", "election", "president", "vote", "democrat", "republican"],
    "animals": ["dog", "cat", "wolf", "bonk", "hat", "wif", "pepe", "frog", "shib", "inu"],
    "sports": ["goat", "ball", "champ", "super bowl", "olympic", "messi", "ronaldo"],
}

# Theme to token symbol whitelist
THEME_TOKENS = {
    "politics": ["TRUMP", "HARRIS", "MELANIA", "BIDEN", "OBAMA", "CLINTON"],
    "animals": ["WIF", "BONK", "POPCAT", "DOGE", "PEPE", "FLOKI", "SHIB"],
    "sports": ["GOAT", "CHAMP", "BALL"],
}

# Relevance scores per mapping type
RELEVANCE_SCORES = {
    "exact_symbol": 1.0,
    "thematic": 0.8,
    "fuzzy_name": 0.6,
}

# Minimum relevance score to include in output
MIN_RELEVANCE_SCORE = 0.6


# =============================================================================
# Text Normalization
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize text for matching:
    - Lowercase
    - Remove punctuation
    - Replace $ with empty (for symbol handling)
    
    Examples:
    - "Will $TRUMP win?" → "will trump win"
    - "Dog-themed memes" → "dog themed memes"
    """
    # Lowercase
    text = text.lower()
    # Remove $ symbol
    text = text.replace("$", "")
    # Remove punctuation and extra whitespace
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_symbols_from_question(question: str) -> List[str]:
    """
    Extract token symbols from question using regex.
    Looks for $SYMBOL pattern.
    
    Examples:
    - "Will $TRUMP win?" → ["TRUMP"]
    - "Vote for $HARRIS or $TRUMP" → ["HARRIS", "TRUMP"]
    """
    pattern = r"\$([A-Z]+)"
    matches = re.findall(pattern, question.upper())
    return list(set(matches))  # Deduplicate


def tokenize_name(name: str) -> Set[str]:
    """
    Tokenize token name into individual words.
    
    Examples:
    - "dogwifhat" → {"dog", "wif", "hat"}
    - "Bonk" → {"bonk"}
    """
    normalized = normalize_text(name)
    # Split on common separators
    tokens = re.split(r"[\s_-]+", normalized)
    return {t for t in tokens if t}


# =============================================================================
# Mapping Strategies
# =============================================================================

def map_exact_symbol(
    market: PolymarketSnapshot,
    tokens: List[TokenSnapshot]
) -> List[MappingResult]:
    """
    Exact symbol matching strategy.
    
    Finds tokens whose symbol appears with $ prefix in the question.
    Returns matches with relevance_score=1.0.
    """
    results = []
    symbols_in_question = extract_symbols_from_question(market.question)
    
    if not symbols_in_question:
        return results
    
    # Create lookup by normalized symbol
    token_by_symbol = {t.symbol.upper(): t for t in tokens}
    
    for symbol in symbols_in_question:
        if symbol in token_by_symbol:
            token = token_by_symbol[symbol]
            results.append(
                MappingResult(
                    market_id=market.id,
                    token_mint=token.mint,
                    token_symbol=token.symbol,
                    relevance_score=RELEVANCE_SCORES["exact_symbol"],
                    mapping_type="exact_symbol",
                    matched_keywords=[symbol],
                )
            )
    
    return results


def map_thematic(
    market: PolymarketSnapshot,
    tokens: List[TokenSnapshot]
) -> List[MappingResult]:
    """
    Thematic matching strategy.
    
    Classifies market by theme keywords, then maps to whitelist of tokens.
    Returns matches with relevance_score=0.8.
    """
    results = []
    normalized_question = normalize_text(market.question)
    
    # Find matching theme
    matched_theme = None
    for theme, keywords in THEMES.items():
        for keyword in keywords:
            if keyword in normalized_question:
                matched_theme = theme
                break
        if matched_theme:
            break
    
    if not matched_theme:
        return results
    
    # Get tokens for this theme
    theme_tokens = THEME_TOKENS.get(matched_theme, [])
    token_by_symbol = {t.symbol.upper(): t for t in tokens}
    
    for symbol in theme_tokens:
        if symbol in token_by_symbol:
            token = token_by_symbol[symbol]
            results.append(
                MappingResult(
                    market_id=market.id,
                    token_mint=token.mint,
                    token_symbol=token.symbol,
                    relevance_score=RELEVANCE_SCORES["thematic"],
                    mapping_type="thematic",
                    matched_keywords=[matched_theme],
                )
            )
    
    return results


def map_fuzzy_name(
    market: PolymarketSnapshot,
    tokens: List[TokenSnapshot]
) -> List[MappingResult]:
    """
    Fuzzy name matching strategy.
    
    Tokenizes token names and matches individual words against question.
    Returns matches with relevance_score=0.6.
    """
    results = []
    normalized_question = normalize_text(market.question)
    question_words = set(normalized_question.split())
    
    for token in tokens:
        token_words = tokenize_name(token.name)
        
        # Find overlapping words
        matched_words = question_words.intersection(token_words)
        
        if matched_words:
            results.append(
                MappingResult(
                    market_id=market.id,
                    token_mint=token.mint,
                    token_symbol=token.symbol,
                    relevance_score=RELEVANCE_SCORES["fuzzy_name"],
                    mapping_type="fuzzy_name",
                    matched_keywords=sorted(list(matched_words)),
                )
            )
    
    return results


# =============================================================================
# Aggregation
# =============================================================================

def build_mappings(
    market: PolymarketSnapshot,
    tokens: List[TokenSnapshot]
) -> List[MappingResult]:
    """
    Build all mappings for a market using all strategies.
    
    Strategies are applied in priority order:
    1. exact_symbol (score=1.0)
    2. thematic (score=0.8)
    3. fuzzy_name (score=0.6)
    
    Deduplication: if a token is matched by multiple strategies,
    keep only the one with highest relevance_score.
    
    Returns deterministic list sorted by:
    - relevance_score DESC
    - token_symbol ASC
    """
    # Collect all results
    all_results: List[MappingResult] = []
    
    # Apply strategies in priority order
    all_results.extend(map_exact_symbol(market, tokens))
    all_results.extend(map_thematic(market, tokens))
    all_results.extend(map_fuzzy_name(market, tokens))
    
    if not all_results:
        return []
    
    # Deduplicate by token (keep highest score)
    best_by_token: dict[str, MappingResult] = {}
    for result in all_results:
        key = result.token_mint
        if key not in best_by_token or result.relevance_score > best_by_token[key].relevance_score:
            best_by_token[key] = result
    
    # Filter by minimum relevance
    filtered = [r for r in best_by_token.values() if r.relevance_score >= MIN_RELEVANCE_SCORE]
    
    # Sort deterministically
    sorted_results = sorted(
        filtered,
        key=lambda x: (-x.relevance_score, x.token_symbol)
    )
    
    return sorted_results


def build_all_mappings(
    markets: List[PolymarketSnapshot],
    tokens: List[TokenSnapshot]
) -> List[MappingResult]:
    """
    Build mappings for all markets.
    
    Deterministic order: markets sorted by ID, then by relevance score.
    """
    all_mappings: List[MappingResult] = []
    
    # Sort markets by ID for deterministic processing
    sorted_markets = sorted(markets, key=lambda x: x.id)
    
    for market in sorted_markets:
        mappings = build_mappings(market, tokens)
        all_mappings.extend(mappings)
    
    return all_mappings


# =============================================================================
# Statistics
# =============================================================================

def compute_mapping_stats(mappings: List[MappingResult]) -> dict:
    """
    Compute statistics for a list of mappings.
    
    Returns dict with:
    - mappings_count: total number of mappings
    - markets_covered: number of unique markets with mappings
    - top_relevance: highest relevance score in results
    - by_type: counts per mapping type
    """
    if not mappings:
        return {
            "mappings_count": 0,
            "markets_covered": 0,
            "top_relevance": 0.0,
            "by_type": {
                "exact_symbol": 0,
                "thematic": 0,
                "fuzzy_name": 0,
            },
        }
    
    markets_set = {m.market_id for m in mappings}
    by_type = {"exact_symbol": 0, "thematic": 0, "fuzzy_name": 0}
    
    for m in mappings:
        by_type[m.mapping_type] = by_type.get(m.mapping_type, 0) + 1
    
    return {
        "mappings_count": len(mappings),
        "markets_covered": len(markets_set),
        "top_relevance": max(m.relevance_score for m in mappings),
        "by_type": by_type,
    }
