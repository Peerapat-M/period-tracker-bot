from unittest.mock import patch

import pytest

import messaging


def test_period_reminder_succeeds_when_push_is_fine():
    with patch.object(messaging.MessagingApi, "push_message") as mock_push:
        messaging.send_period_reminder("u1", "01/09/2026", 1)
    mock_push.assert_called_once()


def test_period_reminder_raises_when_the_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")):
        with pytest.raises(Exception):
            messaging.send_period_reminder("u1", "01/09/2026", 1)


def test_partner_care_does_nothing_when_unpaired():
    with patch.object(messaging.MessagingApi, "push_message") as mock_push, \
         patch.object(messaging.db, "get_partner_id", return_value=None):
        messaging.send_period_reminder_partner_care("u1", "01/09/2026", 1)
    mock_push.assert_not_called()


def test_partner_care_raises_when_the_partner_push_fails():
    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")), \
         patch.object(messaging.db, "get_partner_id", return_value="partner1"):
        with pytest.raises(Exception):
            messaging.send_period_reminder_partner_care("u1", "01/09/2026", 1)


def test_partner_care_raises_when_partner_lookup_itself_errors():
    with patch.object(messaging.MessagingApi, "push_message") as mock_push, \
         patch.object(messaging.db, "get_partner_id", side_effect=Exception("db down")):
        with pytest.raises(Exception):
            messaging.send_period_reminder_partner_care("u1", "01/09/2026", 1)
    mock_push.assert_not_called()


def test_a_partner_only_failure_does_not_touch_the_users_own_push():
    """send_period_reminder and send_period_reminder_partner_care are
    separate jobs precisely so a partner-push failure never causes the
    user's own (already-delivered) reminder to be resent on retry.
    """
    with patch.object(messaging.MessagingApi, "push_message") as mock_push:
        messaging.send_period_reminder("u1", "01/09/2026", 1)

    with patch.object(messaging.MessagingApi, "push_message", side_effect=Exception("down")), \
         patch.object(messaging.db, "get_partner_id", return_value="partner1"):
        with pytest.raises(Exception):
            messaging.send_period_reminder_partner_care("u1", "01/09/2026", 1)

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
