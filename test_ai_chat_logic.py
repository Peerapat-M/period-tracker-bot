import time
from unittest.mock import MagicMock, patch

import pytest

import ai_chat


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    for bucket in ai_chat._recent_call_times.values():
        bucket.clear()
    yield
    for bucket in ai_chat._recent_call_times.values():
        bucket.clear()


@pytest.fixture
def fake_client():
    with patch.object(ai_chat, "_client", MagicMock()):
        yield


@pytest.mark.parametrize("keyword", ["ยา", "รุนแรง", "หนัก", "ผิดปกติ", "อันตราย", "เสี่ยง"])
def test_is_sensitive_topic_matches_known_keywords(keyword):
    assert ai_chat._is_sensitive_topic(f"เรื่อง{keyword}นี้ต้องระวังไหม") is True


def test_is_sensitive_topic_false_for_unrelated_text():
    assert ai_chat._is_sensitive_topic("ประจำเดือนมาช้ากว่าปกติ 2 วัน") is False


def test_global_limit_not_reached_below_threshold():
    for _ in range(ai_chat.GLOBAL_LIMIT_PER_MINUTE - 1):
        ai_chat._recent_call_times[ai_chat.FAST_MODEL].append(time.monotonic())
    assert ai_chat._global_limit_reached(ai_chat.FAST_MODEL) is False


def test_global_limit_reached_at_threshold():
    for _ in range(ai_chat.GLOBAL_LIMIT_PER_MINUTE):
        ai_chat._recent_call_times[ai_chat.FAST_MODEL].append(time.monotonic())
    assert ai_chat._global_limit_reached(ai_chat.FAST_MODEL) is True


def test_global_limit_ignores_calls_older_than_a_minute():
    stale_time = time.monotonic() - 61
    for _ in range(ai_chat.GLOBAL_LIMIT_PER_MINUTE):
        ai_chat._recent_call_times[ai_chat.FAST_MODEL].append(stale_time)
    assert ai_chat._global_limit_reached(ai_chat.FAST_MODEL) is False


def test_get_ai_reply_returns_none_when_client_unconfigured():
    with patch.object(ai_chat, "_client", None):
        assert ai_chat.get_ai_reply("u1", "สวัสดีค่ะ") is None


def test_get_ai_reply_blocks_once_daily_quota_reached(fake_client):
    with patch.object(ai_chat.db, "count_ai_requests_today", return_value=ai_chat.DAILY_LIMIT_PER_USER), \
         patch.object(ai_chat, "_try_model") as mock_try_model:
        result = ai_chat.get_ai_reply("u1", "สวัสดีค่ะ")
    assert result == ai_chat.QUOTA_REACHED_MESSAGE
    mock_try_model.assert_not_called()


def test_get_ai_reply_routes_sensitive_topics_to_careful_model_first(fake_client):
    with patch.object(ai_chat.db, "count_ai_requests_today", return_value=0), \
         patch.object(ai_chat.db, "get_user_logs", return_value=[]), \
         patch.object(ai_chat.db, "log_ai_request") as mock_log, \
         patch.object(ai_chat, "_try_model", return_value="คำตอบ") as mock_try_model:
        ai_chat.get_ai_reply("u1", "กินยาแก้ปวดได้ไหม")
    first_call_model = mock_try_model.call_args_list[0].args[0]
    assert first_call_model == ai_chat.CAREFUL_MODEL
    mock_log.assert_called_once_with("u1")


def test_get_ai_reply_routes_ordinary_topics_to_fast_model_first(fake_client):
    with patch.object(ai_chat.db, "count_ai_requests_today", return_value=0), \
         patch.object(ai_chat.db, "get_user_logs", return_value=[]), \
         patch.object(ai_chat.db, "log_ai_request"), \
         patch.object(ai_chat, "_try_model", return_value="คำตอบ") as mock_try_model:
        ai_chat.get_ai_reply("u1", "ประจำเดือนมาช้าปกติไหม")
    first_call_model = mock_try_model.call_args_list[0].args[0]
    assert first_call_model == ai_chat.FAST_MODEL


def test_get_ai_reply_falls_back_to_busy_message_when_both_models_fail(fake_client):
    with patch.object(ai_chat.db, "count_ai_requests_today", return_value=0), \
         patch.object(ai_chat.db, "get_user_logs", return_value=[]), \
         patch.object(ai_chat.db, "log_ai_request") as mock_log, \
         patch.object(ai_chat, "_try_model", return_value=None):
        result = ai_chat.get_ai_reply("u1", "ประจำเดือนมาช้าปกติไหม")
    assert result == ai_chat.BUSY_MESSAGE
    mock_log.assert_not_called()


def test_get_ai_reply_logs_usage_only_on_success(fake_client):
    with patch.object(ai_chat.db, "count_ai_requests_today", return_value=0), \
         patch.object(ai_chat.db, "get_user_logs", return_value=[]), \
         patch.object(ai_chat.db, "log_ai_request") as mock_log, \
         patch.object(ai_chat, "_try_model", side_effect=[None, "คำตอบจากโมเดลสำรอง"]):
        result = ai_chat.get_ai_reply("u1", "ประจำเดือนมาช้าปกติไหม")
    assert result == "คำตอบจากโมเดลสำรอง"
    mock_log.assert_called_once_with("u1")
