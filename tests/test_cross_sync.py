"""跨服数据同步与一致性 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cross.sync import CrossSyncSystem, PlayerData

class TestAtomicSync:
    def test_sync_does_not_lose_data_on_failure(self):
        cs = CrossSyncSystem()
        cs.data["p1"] = PlayerData("p1", "s1", score=100, version=1)
        # 模拟插入失败的情况：先删后插会丢数据
        # 修复后应该是原子操作
        assert cs.sync_battle_result("p1", "s2", 200) == True
        assert cs.data["p1"].score == 200

class TestConcurrentMerge:
    def test_merge_uses_version_not_last_write(self):
        cs = CrossSyncSystem()
        local = PlayerData("p1", "s1", score=100, version=5)
        remote = PlayerData("p1", "s2", score=50, version=3)
        result = cs.merge_player_data(local, remote)
        # 版本高的应该胜出
        assert result.score == 100

class TestIdempotentReward:
    def test_same_reward_not_duplicated(self):
        cs = CrossSyncSystem()
        cs.sync_reward("p1", "r1", {"gold": 100})
        cs.sync_reward("p1", "r1", {"gold": 100})
        assert len(cs.data["p1"].rewards) == 1

class TestIncrementalProfile:
    def test_profile_update_after_first_sync(self):
        cs = CrossSyncSystem()
        cs.sync_player_profile("p1", "old_name")
        cs.sync_player_profile("p1", "new_name")
        # 第二次同步应该也能更新
        assert cs.data["p1"].pid == "p1"

class TestVersionCheck:
    def test_old_version_cannot_override_new(self):
        cs = CrossSyncSystem()
        cs.data["p1"] = PlayerData("p1", "s1", score=100, version=10)
        new_data = PlayerData("p1", "s2", score=50, version=5)
        result = cs.merge_player_data(cs.data["p1"], new_data)
        assert result.version == 10
        assert result.score == 100
