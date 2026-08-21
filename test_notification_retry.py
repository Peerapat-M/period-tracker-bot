from unittest.mock import patch

import pytest

import messaging


def test_period_reminder_succeeds_when_push_and_partner_lookup_are_fine():
    with patch.object(messaging.MessagingApi, "push_message") as mock_push, \
         patch.object(messaging.db, "get_partner_id", return_value=None):
        messaging.send_period_reminder("u1", "01/09/2026", 1)
    mock_push.assert_called_once()


def test_period_reminder_raises_when_the_users_own_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")), \
         patch.object(messaging.db, "get_partner_id", return_value=None):
        with pytest.raises(Exception):
            messaging.send_period_reminder("u1", "01/09/2026", 1)


def test_period_reminder_raises_when_only_the_partner_push_fails():
    calls = []

    def push_side_effect(request):
        calls.append(request.to)
        if request.to == "partner1":
            raise Exception("partner push down")

    with patch.object(messaging.MessagingApi, "push_message", side_effect=push_side_effect), \
         patch.object(messaging.db, "get_partner_id", return_value="partner1"):
        with pytest.raises(Exception):
            messaging.send_period_reminder("u1", "01/09/2026", 1)
    # Both the user's own push and the partner's push were still attempted --
    # a failure on one doesn't skip the other.
    assert calls == ["u1", "partner1"]


def test_period_reminder_raises_when_partner_lookup_itself_errors():
    with patch.object(messaging.MessagingApi, "push_message") as mock_push, \
         patch.object(messaging.db, "get_partner_id", side_effect=Exception("db down")):
        with pytest.raises(Exception):
            messaging.send_period_reminder("u1", "01/09/2026", 1)
    mock_push.assert_called_once()


def test_late_period_alert_raises_when_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")):
        with pytest.raises(Exception):
            messaging.send_late_period_alert("u1", "01/09/2026")


def test_fertile_window_alert_raises_when_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")):
        with pytest.raises(Exception):
            messaging.send_fertile_window_alert("u1", "01/09/2026", "07/09/2026")


def test_test_date_alert_raises_when_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")):
        with pytest.raises(Exception):
            messaging.send_test_date_alert("u1", "01/09/2026")
