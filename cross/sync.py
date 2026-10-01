"""跨服数据同步与一致性 - 修复版"""
import threading
from dataclasses import dataclass, field

@dataclass
class PlayerData:
    pid: str
    server: str
    score: int = 0
    version: int = 0
    rewards: list = field(default_factory=list)
    nickname: str = ""

class CrossSyncSystem:
    MAX_RETRIES = 3

    def __init__(self):
        self.data: dict[str, PlayerData] = {}
        self.synced_rewards: set = set()  # 幂等键集合: (pid, reward_id)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, pid: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(pid, threading.Lock())

    def sync_battle_result(self, pid: str, server: str, score: int) -> bool:
        # 事务式更新：在锁内就地修改，不再先删后插；失败自动重试
        for _ in range(self.MAX_RETRIES):
            try:
                with self._lock_for(pid):
                    player = self.data.get(pid)
                    if player is None:
                        player = PlayerData(pid, server)
                        self.data[pid] = player
                    player.server = server
                    player.score = score
                    player.version += 1
                return True
            except Exception:
                continue
        return False

    def merge_player_data(self, local: PlayerData, remote: PlayerData) -> PlayerData:
        # 乐观锁：版本号高的胜出，旧版本不能覆盖新版本
        if remote.version > local.version:
            return remote
        return local

    def sync_reward(self, pid: str, reward_id: str, reward: dict) -> bool:
        # 幂等键 (pid, reward_id)：网络重试不会重复发奖
        key = (pid, reward_id)
        with self._lock_for(pid):
            if key in self.synced_rewards:
                return False
            self.synced_rewards.add(key)
            if pid not in self.data:
                self.data[pid] = PlayerData(pid, "unknown")
            self.data[pid].rewards.append(reward)
        return True

    def sync_player_profile(self, pid: str, nickname: str) -> bool:
        # 增量同步：昵称变化时更新，不再只同步第一次
        with self._lock_for(pid):
            player = self.data.get(pid)
            if player is None:
                player = PlayerData(pid, "unknown", nickname=nickname)
                self.data[pid] = player
                return True
            if player.nickname != nickname:
                player.nickname = nickname
                player.version += 1
                return True
        return False
