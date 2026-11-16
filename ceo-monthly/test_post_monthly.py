#!/usr/bin/env python3
"""
Tests for the CEO monthly bot. stdlib unittest, no network, no git.

    cd ceo-monthly && python3 -m unittest -v test_post_monthly
"""

import os
import shutil
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import config
import post_monthly as pm

TZ = pm.TZ


def companies(n, inactive=()):
    return [{"name": f"Co{i}", "handle": f"@co{i}", "active": i not in inactive}
            for i in range(n)]


class Rotation(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.multiple(config, START_YEAR=2026, START_MONTH=12)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_month_is_first_company(self):
        self.assertEqual(pm.company_for((2026, 12), companies(15))["name"], "Co0")

    def test_wraps_after_15(self):
        cos = companies(15)
        self.assertEqual(pm.company_for(pm.add_months((2026, 12), 14), cos)["name"], "Co14")
        self.assertEqual(pm.company_for(pm.add_months((2026, 12), 15), cos)["name"], "Co0")
        self.assertEqual(pm.company_for(pm.add_months((2026, 12), 31), cos)["name"], "Co1")

    def test_inactive_entry_is_skipped(self):
        cos = companies(16, inactive={7})
        names = [pm.company_for(pm.add_months((2026, 12), n), cos)["name"] for n in range(16)]
        self.assertNotIn("Co7", names)
        self.assertEqual(names[6], "Co6")
        self.assertEqual(names[7], "Co8")
        # 15 active, so month 15 wraps to the top.
        self.assertEqual(names[15], "Co0")

    def test_every_active_company_once_per_cycle(self):
        cos = companies(16, inactive={7})
        names = [pm.company_for(pm.add_months((2026, 12), n), cos)["name"] for n in range(15)]
        self.assertEqual(len(set(names)), 15)

    def test_before_start_is_an_error(self):
        with self.assertRaises(ValueError):
            pm.company_for((2026, 11), companies(15))

    def test_no_active_companies_is_an_error(self):
        with self.assertRaises(ValueError):
            pm.company_for((2026, 12), companies(3, inactive={0, 1, 2}))

    def test_year_boundary(self):
        self.assertEqual(pm.add_months((2026, 12), 1), (2027, 1))
        self.assertEqual(pm.months_since_start((2028, 3)), 15)

    def test_template_from_config(self):
        company = {"name": "Apple", "handle": "@Apple", "active": True}
        self.assertEqual(pm.build_tweet(company, "Relai users hold more Bitcoin than {handle}"),
                         "Relai users hold more Bitcoin than @Apple")

    def test_shipped_config_is_valid(self):
        pm.validate_config()
        self.assertEqual(len(pm.active_companies()), 15)


class Schedule(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.multiple(config, POST_WEEKDAY=1, POST_WEEK=1,
                                      POST_HOUR=13, POST_MINUTE=58, HEADS_UP_DAYS=3)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_tuesday(self):
        self.assertEqual(pm.post_datetime((2026, 12)).date(), date(2026, 12, 1))
        self.assertEqual(pm.post_datetime((2027, 1)).date(), date(2027, 1, 5))
        self.assertEqual(pm.post_datetime((2027, 6)).date(), date(2027, 6, 1))

    def test_dst(self):
        winter = pm.post_datetime((2027, 3))   # 2 Mar, CET
        summer = pm.post_datetime((2027, 7))   # 6 Jul, CEST
        self.assertEqual(winter.utcoffset().total_seconds(), 3600)
        self.assertEqual(summer.utcoffset().total_seconds(), 7200)
        self.assertEqual((winter.hour, winter.minute), (13, 58))
        self.assertEqual((summer.hour, summer.minute), (13, 58))

    def test_heads_up_date_can_fall_in_previous_month(self):
        self.assertEqual(pm.heads_up_date((2026, 12)), date(2026, 11, 28))

    def test_cron_slots_cover_default_time_in_both_seasons(self):
        for month in range(1, 13):
            self.assertTrue(pm.post_time_covered((2027, month)), month)

    def test_uncovered_time_is_detected(self):
        with mock.patch.object(config, "POST_HOUR", 9):
            self.assertFalse(pm.post_time_covered((2027, 1)))


class WithLogs(unittest.TestCase):
    """Points the three log files at a temp dir and stubs out git, Slack and X."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for name in ("POSTED_FILE", "NOTICES_FILE"):
            p = mock.patch.object(pm, name, os.path.join(self.tmp, name.lower()))
            p.start()
            self.addCleanup(p.stop)
        patches = [
            mock.patch.multiple(config, START_YEAR=2026, START_MONTH=12, POST_WEEKDAY=1,
                                POST_WEEK=1, POST_HOUR=13, POST_MINUTE=58,
                                HEADS_UP_DAYS=3, HARD_CUTOFF_HOUR=20),
            mock.patch.object(pm, "commit"),
            mock.patch.object(pm, "send_slack"),
            mock.patch.object(pm.x_api, "get_credentials", return_value={}),
            mock.patch.object(pm.x_api, "already_posted", return_value=False),
            mock.patch.object(pm.x_api, "post", return_value="123"),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.slack = self.mocks[2]
        self.already = self.mocks[4]
        self.post = self.mocks[5]
        env = mock.patch.dict(os.environ, {"GITHUB_ACTOR": "tester"})
        env.start()
        self.addCleanup(env.stop)

    DEC = (2026, 12)
    POST_TIME = datetime(2026, 12, 1, 14, 5, tzinfo=TZ)


class DoublePostGuard(WithLogs):
    def test_posts_once(self):
        pm.run_scheduled(self.POST_TIME, dry_run=False)
        self.assertEqual(self.post.call_count, 1)
        self.assertTrue(pm.is_posted(self.DEC))

    def test_second_slot_same_day_does_not_post(self):
        pm.run_scheduled(self.POST_TIME, dry_run=False)
        pm.run_scheduled(datetime(2026, 12, 1, 15, 41, tzinfo=TZ), dry_run=False)
        self.assertEqual(self.post.call_count, 1)

    def test_already_on_account_logs_without_posting(self):
        # A post that went out but whose log push failed.
        self.already.return_value = True
        pm.run_scheduled(self.POST_TIME, dry_run=False)
        self.post.assert_not_called()
        self.assertTrue(pm.is_posted(self.DEC))

    def test_post_now_respects_log(self):
        pm.post_now(self.DEC, dry_run=False)
        pm.post_now(self.DEC, dry_run=False)
        self.assertEqual(self.post.call_count, 1)

    def test_dry_run_never_calls_x(self):
        pm.run_scheduled(self.POST_TIME, dry_run=True)
        pm.post_now(self.DEC, dry_run=True)
        self.post.assert_not_called()
        self.assertFalse(pm.is_posted(self.DEC))


class HeadsUpAndTiming(WithLogs):
    def test_posts_with_no_approval_step(self):
        pm.run_scheduled(self.POST_TIME, dry_run=False)
        self.assertEqual(self.post.call_count, 1)

    def test_too_early_on_post_day(self):
        pm.run_scheduled(datetime(2026, 12, 1, 12, 58, tzinfo=TZ), dry_run=False)
        self.post.assert_not_called()
        self.slack.assert_not_called()

    def test_past_cutoff_sends_missed_once_and_does_not_post(self):
        pm.run_scheduled(datetime(2026, 12, 1, 20, 30, tzinfo=TZ), dry_run=False)
        pm.run_scheduled(datetime(2026, 12, 2, 13, 0, tzinfo=TZ), dry_run=False)
        self.post.assert_not_called()
        self.assertEqual(self.slack.call_count, 1)
        self.assertIn("did not go out", self.slack.call_args[0][0])

    def test_heads_up_sent_once_three_days_before(self):
        pm.run_scheduled(datetime(2026, 11, 27, 14, 0, tzinfo=TZ), dry_run=False)
        self.slack.assert_not_called()
        pm.run_scheduled(datetime(2026, 11, 28, 14, 0, tzinfo=TZ), dry_run=False)
        pm.run_scheduled(datetime(2026, 11, 28, 15, 0, tzinfo=TZ), dry_run=False)
        self.assertEqual(self.slack.call_count, 1)
        message = self.slack.call_args[0][0]
        self.assertIn("Relai holds more Bitcoin than @Apple", message)
        self.assertIn("bitcointreasuries", message)
        self.assertIn("No action needed", message)
        self.post.assert_not_called()

    def test_missed_heads_up_day_is_caught_up(self):
        pm.run_scheduled(datetime(2026, 11, 30, 14, 0, tzinfo=TZ), dry_run=False)
        self.assertEqual(self.slack.call_count, 1)

    def test_no_heads_up_for_a_month_already_posted(self):
        pm.post_now(self.DEC, dry_run=False)
        self.slack.reset_mock()
        pm.run_scheduled(datetime(2026, 11, 28, 14, 0, tzinfo=TZ), dry_run=False)
        self.slack.assert_not_called()

    def test_wording_change_posts_new_wording(self):
        with mock.patch.object(config, "TEMPLATE", "Relai users hold more Bitcoin than {handle}"):
            pm.run_scheduled(self.POST_TIME, dry_run=False)
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args[0][1], "Relai users hold more Bitcoin than @Apple")


if __name__ == "__main__":
    unittest.main()
