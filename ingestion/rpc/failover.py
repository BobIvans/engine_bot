"""
ingestion/rpc/failover.py

Failover Manager — ротация эндпоинтов и выбор "лучшего" в реальном времени.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .monitor import HealthMonitor, HealthScore

logger = logging.getLogger(__name__)


@dataclass
class EndpointConfig:
    """Конфигурация эндпоинта."""
    url: str
    priority: int = 0  # Lower = higher priority
    is_primary: bool = False


class FailoverManager:
    """
    Менеджер переключения между RPC провайдерами.
    
    Features:
    - Приоритетный список эндпоинтов
    - Health-based selection
    - Automatic failover на резервные при сбоях
    - Deterministic selection (no randomness)
    
    PR-T.2
    """
    
    def __init__(
        self,
        health_monitor: Optional[HealthMonitor] = None,
    ):
        """
        Initialize FailoverManager.
        
        Args:
            health_monitor: Optional HealthMonitor instance
        """
        self._endpoints: Dict[str, EndpointConfig] = {}
        self._health_monitor = health_monitor
        
        # Current active endpoint
        self._active_endpoint: Optional[str] = None
        self._last_switch_time: Optional[float] = None
        
    def add_endpoint(self, url: str, priority: int = 0, is_primary: bool = False) -> None:
        """
        Добавить эндпоинт в пул.
        
        Args:
            url: URL эндпоинта
            priority: Приоритет (0 = highest)
            is_primary: Является ли основным провайдером
        """
        self._endpoints[url] = EndpointConfig(
            url=url,
            priority=priority,
            is_primary=is_primary,
        )
        
        # Register with health monitor if available
        if self._health_monitor is not None:
            self._health_monitor.add_endpoint(url)
        
        logger.info(f"[failover] Added endpoint: {url} (priority={priority}, primary={is_primary})")
    
    def remove_endpoint(self, url: str) -> bool:
        """Удалить эндпоинт из пула."""
        if url in self._endpoints:
            del self._endpoints[url]
            if self._active_endpoint == url:
                self._active_endpoint = None
            logger.info(f"[failover] Removed endpoint: {url}")
            return True
        return False
    
    def set_health_monitor(self, monitor: HealthMonitor) -> None:
        """Установить HealthMonitor."""
        self._health_monitor = monitor
        # Register all endpoints
        for url in self._endpoints:
            monitor.add_endpoint(url)
    
    def get_active_endpoint(self) -> Optional[str]:
        """
        Получить активный эндпоинт (с наивысшим health score).
        
        Returns:
            URL активного эндпоинта или None
        """
        if not self._endpoints:
            return None
        
        # Если есть активный и он здоров, продолжаем использовать
        if self._active_endpoint is not None:
            score = self._get_score(self._active_endpoint)
            if score is not None and score.score > 50:  # Threshold for healthy
                return self._active_endpoint
        
        # Ищем лучший эндпоинт
        best = self._select_best()
        
        if best != self._active_endpoint:
            self._switch_endpoint(best)
        
        return best
    
    def _select_best(self) -> Optional[str]:
        """Выбрать лучший эндпоинт на основе health score и приоритета."""
        candidates = []
        
        for url, config in self._endpoints.items():
            score = self._get_score(url)
            if score is not None:
                # Effective score = health score + priority bonus
                effective_score = score.score - (config.priority * 10)
                candidates.append((effective_score, config.priority, url))
            else:
                # No health data, use priority
                candidates.append((-config.priority * 10, config.priority, url))
        
        if not candidates:
            return list(self._endpoints.keys())[0] if self._endpoints else None
        
        # Sort by effective score (descending), then by priority (ascending)
        candidates.sort(key=lambda x: (-x[0], x[1]))
        
        return candidates[0][2]
    
    def _get_score(self, url: str) -> Optional[HealthScore]:
        """Get health score for endpoint."""
        if self._health_monitor is None:
            return None
        return self._health_monitor.get_score(url)
    
    def _switch_endpoint(self, new_url: Optional[str]) -> None:
        """Переключиться на новый эндпоинт."""
        old_url = self._active_endpoint
        self._active_endpoint = new_url
        self._last_switch_time = __import__('time').time()
        
        if new_url is not None:
            logger.warning(f"[failover] Switching from {old_url} to {new_url}")
        else:
            logger.error("[failover] No healthy endpoints available!")
    
    def report_failure(self, url: str) -> None:
        """
        Report failure for endpoint and switch if necessary.
        
        Args:
            url: URL эндпоинта
        """
        if self._health_monitor is not None:
            self._health_monitor.report_failure(url)
        
        # Check if we need to switch
        if self._active_endpoint == url:
            score = self._get_score(url)
            if score is not None and score.score <= 0:
                best = self._select_best()
                if best != url:
                    self._switch_endpoint(best)
    
    def report_success(self, url: str) -> None:
        """Report success for endpoint."""
        if self._health_monitor is not None:
            self._health_monitor.report_success(url)
    
    def get_status(self) -> Dict[str, Any]:
        """Get failover manager status."""
        scores = {}
        if self._health_monitor:
            all_scores = self._health_monitor.get_all_scores()
            for url, score in all_scores.items():
                scores[url] = score.to_dict()
        
        return {
            "endpoints": {url: {
                "priority": cfg.priority,
                "is_primary": cfg.is_primary,
            } for url, cfg in self._endpoints.items()},
            "active_endpoint": self._active_endpoint,
            "scores": scores,
            "last_switch": self._last_switch_time,
        }
    
    def get_endpoints(self) -> List[str]:
        """Get list of all endpoint URLs."""
        return list(self._endpoints.keys())
    
    def get_healthy_endpoints(self) -> List[str]:
        """Get list of healthy endpoint URLs."""
        healthy = []
        for url in self._endpoints:
            score = self._get_score(url)
            if score is not None and score.score > 0:
                healthy.append(url)
        return healthy
    
    def __contains__(self, url: str) -> bool:
        """Check if endpoint exists."""
        return url in self._endpoints
    
    def __len__(self) -> int:
        """Get number of endpoints."""
        return len(self._endpoints)
