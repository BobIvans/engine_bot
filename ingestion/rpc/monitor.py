"""
ingestion/rpc/monitor.py

Health Monitor — периодическая проверка latency и availability эндпоинтов.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class HealthScore:
    """Health score для RPC эндпоинта."""
    url: str
    score: float = 100.0
    latency_ms: float = 0.0
    errors: int = 0
    successes: int = 0
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'url': self.url,
            'score': self.score,
            'latency_ms': self.latency_ms,
            'errors': self.errors,
            'successes': self.successes,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'last_error': self.last_error.isoformat() if self.last_error else None,
        }


class HealthMonitor:
    """
    Мониторинг здоровья RPC эндпоинтов.
    
    Features:
    - Background thread для периодических checks
    - Health score calculation
    - Latency tracking
    - Error tracking
    
    PR-T.2
    """
    
    DEFAULT_INTERVAL_SEC = 30  # Интервал между проверками
    ERROR_PENALTY = 20        # Штраф за ошибку
    LATENCY_PENALTY_FACTOR = 0.1  # Штраф за latency (latency / 10)
    RECOVERY_BONUS = 5         # Бонус за успешный check при восстановлении
    
    def __init__(
        self,
        health_check_callable: Callable[[str], Dict[str, Any]],
        interval_sec: int = DEFAULT_INTERVAL_SEC,
    ):
        """
        Initialize HealthMonitor.
        
        Args:
            health_check_callable: Function that takes URL and returns health check result
            interval_sec: Interval between health checks (seconds)
        """
        self._callable = health_check_callable
        self._interval_sec = interval_sec
        
        self._scores: Dict[str, HealthScore] = {}
        self._lock = threading.RLock()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
    def add_endpoint(self, url: str, initial_score: float = 100.0) -> HealthScore:
        """Добавить эндпоинт для мониторинга."""
        with self._lock:
            if url not in self._scores:
                self._scores[url] = HealthScore(url=url, score=initial_score)
            return self._scores[url]
    
    def remove_endpoint(self, url: str) -> bool:
        """Удалить эндпоинт из мониторинга."""
        with self._lock:
            if url in self._scores:
                del self._scores[url]
                return True
            return False
    
    def check_endpoint(self, url: str) -> HealthScore:
        """
        Выполнить health check для эндпоинта.
        
        Args:
            url: URL эндпоинта
            
        Returns:
            Updated HealthScore
        """
        start_time = time.time()
        error = None
        success = False
        
        try:
            result = self._callable(url)
            # Assume success if no exception and result is valid
            success = True
            latency_ms = (time.time() - start_time) * 1000
        except Exception as e:
            error = e
            latency_ms = (time.time() - start_time) * 1000
            # Cap latency at 10 seconds for errors
            latency_ms = min(latency_ms, 10000)
        
        with self._lock:
            if url not in self._scores:
                self._scores[url] = HealthScore(url=url)
            
            score = self._scores[url]
            score.latency_ms = latency_ms
            score.last_check = datetime.utcnow()
            
            if success:
                score.successes += 1
                score.last_success = datetime.utcnow()
                # Calculate score: 100 - (errors * 20) - (latency / 10)
                base_score = 100.0 - (score.errors * self.ERROR_PENALTY)
                score.score = max(0, base_score - (latency_ms * self.LATENCY_PENALTY_FACTOR))
            else:
                score.errors += 1
                score.last_error = datetime.utcnow()
                # Immediate penalty for errors
                score.score = max(0, 100.0 - (score.errors * self.ERROR_PENALTY))
            
            return score
    
    def report_success(self, url: str) -> None:
        """Report successful request for endpoint."""
        with self._lock:
            if url in self._scores:
                score = self._scores[url]
                score.successes += 1
                score.last_success = datetime.utcnow()
                # Gradual recovery
                if score.errors > 0:
                    score.errors = max(0, score.errors - 0.5)  # Half error count
                base_score = 100.0 - (score.errors * self.ERROR_PENALTY)
                score.score = max(0, base_score - (score.latency_ms * self.LATENCY_PENALTY_FACTOR))
    
    def report_failure(self, url: str) -> None:
        """Report failed request for endpoint."""
        with self._lock:
            if url not in self._scores:
                self._scores[url] = HealthScore(url=url)
            
            score = self._scores[url]
            score.errors += 1
            score.last_error = datetime.utcnow()
            # Immediate penalty
            score.score = max(0, 100.0 - (score.errors * self.ERROR_PENALTY))
            logger.warning(f"[health_monitor] Error reported for {url}, score: {score.score:.1f}")
    
    def start_background_monitoring(self) -> None:
        """Start background thread for periodic health checks."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._background_loop, daemon=True)
        self._thread.start()
        logger.info("[health_monitor] Background monitoring started")
    
    def stop_background_monitoring(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("[health_monitor] Background monitoring stopped")
    
    def _background_loop(self) -> None:
        """Background loop for periodic checks."""
        while self._running:
            with self._lock:
                urls = list(self._scores.keys())
            
            for url in urls:
                if not self._running:
                    break
                try:
                    self.check_endpoint(url)
                except Exception as e:
                    logger.error(f"[health_monitor] Check failed for {url}: {e}")
            
            # Wait for next interval
            time.sleep(self._interval_sec)
    
    def get_score(self, url: str) -> Optional[HealthScore]:
        """Get health score for endpoint."""
        with self._lock:
            return self._scores.get(url)
    
    def get_all_scores(self) -> Dict[str, HealthScore]:
        """Get all health scores."""
        with self._lock:
            return dict(self._scores)
    
    def get_best_endpoint(self) -> Optional[str]:
        """Get URL with highest health score."""
        with self._lock:
            if not self._scores:
                return None
            best = max(self._scores.values(), key=lambda s: s.score)
            return best.url if best.score > 0 else None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get monitoring metrics."""
        with self._lock:
            total_errors = sum(s.errors for s in self._scores.values())
            total_successes = sum(s.successes for s in self._scores.values())
            avg_score = (
                sum(s.score for s in self._scores.values()) / len(self._scores)
                if self._scores
                else 0
            )
            return {
                "endpoints": len(self._scores),
                "total_errors": total_errors,
                "total_successes": total_successes,
                "average_score": avg_score,
                "running": self._running,
            }
