"""跨服数据同步与一致性 - 含5个bug"""
from dataclasses import dataclass, field

@dataclass
class PlayerData:
    pid: str
    server: str
    score: int = 0
    version: int = 0  # bug5: 不检查版本
    rewards: list = field(default_factory=list)

class CrossSyncSystem:
    def __init__(self):
        self.data: dict[str, PlayerData] = {}
        self.synced_rewards: set = set()  # bug3: 无幂等

    def sync_battle_result(self, pid: str, server: str, score: int) -> bool:
        # bug1: 先删后插，非原子
        if pid in self.data:
            del self.data[pid]
        self.data[pid] = PlayerData(pid, server, score)
        return True

    def merge_player_data(self, local: PlayerData, remote: PlayerData) -> PlayerData:
        # bug2: 并发冲突，后写覆盖先写；bug5: 不检查版本号
        return remote

    def sync_reward(self, pid: str, reward_id: str, reward: dict) -> bool:
        # bug3: 无幂等键，重复发奖励
        if pid not in self.data:
            self.data[pid] = PlayerData(pid, "unknown")
        self.data[pid].rewards.append(reward)
        return True

    def sync_player_profile(self, pid: str, nickname: str) -> bool:
        # bug4: 只同步一次，无增量
        if pid not in self.data:
            self.data[pid] = PlayerData(pid, "unknown")
            return True
        return False
