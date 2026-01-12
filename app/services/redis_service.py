from __future__ import annotations
import time
from typing import Dict, Optional

import redis

from app.core.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_KEY_PREFIX,
    CALL_STATE_TTL_SECONDS,
)
from app.core.constants import STATE_INIT, STATE_COMPLETED


# ============================================================
# In-Memory Redis Fallback (DEV / EMERGENCY ONLY)
# ============================================================
class MemoryRedis:
    """
    DEV-only fallback.
    Mimics minimal redis-py behavior.
    Data is lost on restart.
    """

    # Shared across all instances in the same process
    _data: Dict[str, Dict[str, str]] = {}
    _expires: Dict[str, float] = {}

    def __init__(self):
        print("WARNING: Using In-Memory Redis Fallback (DEV ONLY)")

    def _check_expiry(self, key: str):
        if key in self._expires and time.time() > self._expires[key]:
            self.delete(key)

    def hgetall(self, key: str) -> Dict[str, str]:
        self._check_expiry(key)
        return self._data.get(key, {}).copy()

    def hset(self, name: str, key: str = None, value: str = None, mapping: Dict = None) -> int:
        # Support both signatures:
        # 1. hset(name, key, value)
        # 2. hset(name, mapping={...})
        
        target_key = name
        self._check_expiry(target_key)
        
        if target_key not in self._data:
            self._data[target_key] = {}
            
        data_to_add = {}
        if mapping:
            data_to_add.update(mapping)
        if key and value:
            data_to_add[key] = value
            
        for k, v in data_to_add.items():
            self._data[target_key][str(k)] = str(v)
            
        return len(data_to_add)

    def exists(self, key: str) -> int:
        self._check_expiry(key)
        return 1 if key in self._data else 0

    def expire(self, key: str, seconds: int) -> bool:
        if key not in self._data:
            return False
        self._expires[key] = time.time() + seconds
        return True

    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        self._check_expiry(key)
        if key not in self._data:
            self._data[key] = {}
        current = int(self._data[key].get(field, 0))
        new_val = current + amount
        self._data[key][field] = str(new_val)
        return new_val

    def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
            self._expires.pop(key, None)
        return count


# ============================================================
# Redis Service (PRODUCTION SAFE)
# ============================================================
class RedisService:
    """
    Thin Redis abstraction.

    RULES:
    - NO business logic
    - NO decisions
    - ONLY state + counters
    - HARD type safety
    - AUTO fallback to memory in DEV
    """

    def __init__(self) -> None:
        try:
            self.client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
                health_check_interval=0,
                retry_on_timeout=False,
                retry=None, # Disable all retries
            )
            # Try a lightweight operation instead of ping
            self.client.exists("probe")
        except (redis.ConnectionError, redis.TimeoutError, Exception):
            self.client = MemoryRedis()

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _key(self, call_id: str) -> str:
        return f"{REDIS_KEY_PREFIX}:{str(call_id)}"

    # -----------------------------
    # Call state APIs
    # -----------------------------
    def get_call_state(self, call_id: str) -> Dict[str, str]:
        return self.client.hgetall(self._key(call_id)) or {}

    def initialize_call_if_missing(self, call_id: str) -> Dict[str, str]:
        key = self._key(call_id)

        if not self.client.exists(key):
            now = int(time.time())
            self.client.hset(
                key,
                mapping={
                    "state": STATE_INIT,
                    "retry_count": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            self.client.expire(key, CALL_STATE_TTL_SECONDS)

        return self.get_call_state(call_id)

    def update_call_state(
        self,
        call_id: str,
        *,
        state: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> Dict[str, str]:
        key = self._key(call_id)

        # HARD cleanup on terminal state
        if state == STATE_COMPLETED:
            self.client.delete(key)
            return {}

        now = int(time.time())
        updates: Dict[str, str] = {"updated_at": str(now)}

        if state is not None:
            updates["state"] = str(state)

        if retry_count is not None:
            updates["retry_count"] = str(retry_count)

        self.client.hset(key, mapping=updates)
        self.client.expire(key, CALL_STATE_TTL_SECONDS)

        return self.get_call_state(call_id)

    def increment_retry(self, call_id: str) -> int:
        key = self._key(call_id)
        new_val = self.client.hincrby(key, "retry_count", 1)
        self.client.expire(key, CALL_STATE_TTL_SECONDS)
        return int(new_val)

    # -----------------------------
    # Advanced Day-3 Features
    # -----------------------------
    def record_sla_metric(self, *, metric_name: str, value: str, window_seconds: int = 3600) -> None:
        """
        Records a metric in a sliding window (Redis List).
        """
        key = f"sla:window:{metric_name}"
        now = time.time()
        
        # Add new event with timestamp
        data = f"{now}:{value}"
        
        if isinstance(self.client, MemoryRedis):
            if key not in self.client._data:
                self.client._data[key] = {"events": ""}
            events = self.client._data[key]["events"].split(",") if self.client._data[key]["events"] else []
            events.append(data)
            self.client._data[key]["events"] = ",".join(events)
        else:
            self.client.rpush(key, data)
            self.client.expire(key, window_seconds + 60)

    def get_sla_metrics(self, *, metric_name: str, window_seconds: int = 3600) -> list[str]:
        """
        Retrieves all valid metrics within the window.
        """
        key = f"sla:window:{metric_name}"
        now = time.time()
        cutoff = now - window_seconds
        
        valid_values = []
        
        if isinstance(self.client, MemoryRedis):
            events = self.client._data.get(key, {}).get("events", "").split(",")
            events = [e for e in events if e]
            updated_events = []
            for event in events:
                try:
                    ts, val = event.split(":")
                    if float(ts) >= cutoff:
                        valid_values.append(val)
                        updated_events.append(event)
                except ValueError:
                    continue
            self.client._data.setdefault(key, {})["events"] = ",".join(updated_events)
        else:
            # Production Redis: cleanup and fetch
            all_events = self.client.lrange(key, 0, -1)
            # Simple cleanup for production (LPOP if oldest is expired)
            # In a real system, we might use ZSET for better performance
            valid_events = []
            for event in all_events:
                try:
                    ts, val = event.split(":")
                    if float(ts) >= cutoff:
                        valid_values.append(val)
                        valid_events.append(event)
                except ValueError:
                    continue
            
            # Atomic update not easy with lists, but for this agentic system it's enough
            self.client.delete(key)
            if valid_events:
                self.client.rpush(key, *valid_events)
                self.client.expire(key, window_seconds + 60)
                
        return valid_values

    def check_load_concurrency(self, max_concurrency: int) -> bool:
        """
        Semaphore-style concurrency check.
        """
        key = "load:active_calls"
        
        if isinstance(self.client, MemoryRedis):
            current = int(self.client._data.get(key, {}).get("count", 0))
            if current < max_concurrency:
                self.client.hincrby(key, "count", 1)
                return True
            return False
        else:
            # Use Redis INCR and compare (Atomic)
            current = self.client.incr(key)
            if current > max_concurrency:
                self.client.decr(key)
                return False
            return True

    def release_load_concurrency(self) -> None:
        """
        Decrement active calls.
        """
        key = "load:active_calls"
        if isinstance(self.client, MemoryRedis):
            self.client.hincrby(key, "count", -1)
        else:
            self.client.decr(key)

    def get_active_calls_count(self) -> int:
        """
        Returns the current number of active calls.
        """
        key = "load:active_calls"
        if isinstance(self.client, MemoryRedis):
            return int(self.client._data.get(key, {}).get("count", 0))
        else:
            val = self.client.get(key)
            return int(val) if val else 0

    # -----------------------------
    # Step 3: Shared State & Team Dynamics
    # -----------------------------
    def get_team_state(self, call_id: str) -> Dict[str, Any]:
        """
        Retrieve the shared state object for a specific call.
        """
        import json
        key = f"team_state:{call_id}"
        if isinstance(self.client, MemoryRedis):
            raw_state = self.client._data.get(key, {}).get("data")
        else:
            raw_state = self.client.get(key)
        
        return json.loads(raw_state) if raw_state else {}

    def update_team_state(self, call_id: str, updates: Dict[str, Any]) -> None:
        """
        Atomically update the shared state for a call.
        """
        import json
        key = f"team_state:{call_id}"
        
        if isinstance(self.client, MemoryRedis):
            current_state = self.get_team_state(call_id)
            current_state.update(updates)
            if key not in self.client._data:
                self.client._data[key] = {}
            self.client._data[key]["data"] = json.dumps(current_state)
            self.client._expires[key] = time.time() + 3600
        else:
            with self.client.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(key)
                        current_state = self.get_team_state(call_id)
                        current_state.update(updates)
                        pipe.multi()
                        pipe.set(key, json.dumps(current_state), ex=3600)  # Standard 1hr TTL
                        pipe.execute()
                        break
                    except redis.WatchError:
                        continue
