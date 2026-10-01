"""跨服数据同步与一致性。

修复点：
1. sync_battle_result：单键原地更新（构造完成后再入存储），不再先删后插，
   任何失败都不会清空旧数据；通过版本号做乐观锁（CAS），冲突返回 False 由调用方重试。
2. merge_player_data：按版本号取新，旧版本数据无法覆盖新版本；同版本保守保留本服。
3. sync_reward：以 (pid, reward_id) 为幂等键，超时重试不会重复发奖。
4. sync_player_profile：每次调用都做增量更新，昵称/头像变更立即同步。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


class OptimisticLockConflict(Exception):
    """乐观锁冲突：存储中的版本号与调用方期望的版本号不一致。"""


@dataclass
class PlayerData:
    pid: str
    server: str
    score: int = 0
    version: int = 0
    rewards: list = field(default_factory=list)
    nickname: Optional[str] = None
    avatar: Optional[str] = None


class CrossSyncSystem:
    def __init__(self):
        self.data: dict[str, PlayerData] = {}
        # 奖励幂等键：(pid, reward_id)
        self.synced_rewards: set[tuple[str, str]] = set()
        # 资料版本：pid -> 已同步资料的版本号，防止旧资料回灌
        self.profile_versions: dict[str, int] = {}
        self._lock = threading.RLock()

    def sync_battle_result(
        self,
        pid: str,
        server: str,
        score: int,
        expected_version: Optional[int] = None,
    ) -> bool:
        """原子地写入战斗结果。

        - 不再先删后插：先在原对象上完成全部字段更新（或先构造好新对象再放入
          dict），中途失败旧数据保持完整。
        - 乐观锁：传入 expected_version 时，只有与当前 version 一致才写入；
          不一致返回 False（调用方可重新读取最新版本后重试），不覆盖任何人的数据。
        - 写入成功后 version 加 1。
        """
        with self._lock:
            current = self.data.get(pid)
            if current is not None and expected_version is not None:
                if current.version != expected_version:
                    return False
            new_version = (current.version if current is not None else 0) + 1
            updated = PlayerData(
                pid=pid,
                server=server,
                score=score,
                version=new_version,
                rewards=list(current.rewards) if current is not None else [],
                nickname=current.nickname if current is not None else None,
                avatar=current.avatar if current is not None else None,
            )
            # 单条 dict 赋值，保证存储切换的原子性，不存在“删掉了但没插进去”的窗口
            self.data[pid] = updated
            return True

    def merge_player_data(self, local: PlayerData, remote: PlayerData) -> PlayerData:
        """按版本号合并：版本高的数据整体胜出；同版本保留本服数据。"""
        if remote.version > local.version:
            return remote
        return local

    def sync_reward(self, pid: str, reward_id: str, reward: dict) -> bool:
        """同步奖励，带幂等键。

        同一个 (pid, reward_id) 只发一次；网络超时后的重试命中幂等键会被忽略。
        返回 True 表示本次实际发放，False 表示此前已发放过（重复请求）。
        """
        key = (pid, reward_id)
        with self._lock:
            if key in self.synced_rewards:
                return False
            player = self.data.get(pid)
            if player is None:
                player = PlayerData(pid, "unknown")
                self.data[pid] = player
            player.rewards.append(reward)
            self.synced_rewards.add(key)
            return True

    def sync_player_profile(
        self,
        pid: str,
        nickname: Optional[str] = None,
        avatar: Optional[str] = None,
        profile_version: Optional[int] = None,
    ) -> bool:
        """增量同步玩家资料（昵称/头像）。

        不再只在首次跨服时写入：每次调用都会把新昵称/头像更新过去。
        可选 profile_version 进一步保证旧版本资料不能回灌新版本。
        返回 True 表示资料发生了更新，False 表示无变化或资料过期被拒绝。
        """
        with self._lock:
            if profile_version is not None:
                seen = self.profile_versions.get(pid)
                if seen is not None and profile_version < seen:
                    return False
            player = self.data.get(pid)
            if player is None:
                player = PlayerData(pid, "unknown")
                self.data[pid] = player
            changed = False
            if nickname is not None and nickname != player.nickname:
                player.nickname = nickname
                changed = True
            if avatar is not None and avatar != player.avatar:
                player.avatar = avatar
                changed = True
            if profile_version is not None:
                self.profile_versions[pid] = profile_version
            return changed
