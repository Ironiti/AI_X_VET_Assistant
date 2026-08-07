import unittest

from bot.telegram_proxy import (
    build_proxy_candidates,
    env_flag_enabled,
    mask_proxy,
    select_telegram_proxy,
)


class TelegramProxySelectionTests(unittest.TestCase):
    def test_build_proxy_candidates_keeps_primary_then_reserve(self):
        candidates = build_proxy_candidates("socks5://primary", "socks5://reserve")

        self.assertEqual([candidate.name for candidate in candidates], ["primary", "reserve"])
        self.assertEqual([candidate.url for candidate in candidates], ["socks5://primary", "socks5://reserve"])

    def test_build_proxy_candidates_deduplicates_same_url(self):
        candidates = build_proxy_candidates("socks5://same", "socks5://same")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "primary")

    def test_mask_proxy_hides_credentials(self):
        self.assertEqual(mask_proxy("socks5://user:pass@example.com:8000"), "socks5://***@example.com:8000")

    def test_env_flag_enabled_parses_false_values(self):
        self.assertFalse(env_flag_enabled("0"))
        self.assertFalse(env_flag_enabled("false"))
        self.assertTrue(env_flag_enabled("1"))

    def test_select_uses_primary_without_reserve_preflight(self):
        calls = []

        def checker(token, proxy, timeout):
            calls.append(proxy)
            return True, "ok"

        selected = select_telegram_proxy(
            bot_token="token",
            primary_proxy_url="socks5://primary",
            reserve_proxy_url="",
            checker=checker,
        )

        self.assertEqual(selected, "socks5://primary")
        self.assertEqual(calls, [])

    def test_select_falls_back_to_reserve_when_primary_fails(self):
        def checker(token, proxy, timeout):
            return proxy == "socks5://reserve", "ok" if proxy == "socks5://reserve" else "fail"

        selected = select_telegram_proxy(
            bot_token="token",
            primary_proxy_url="socks5://primary",
            reserve_proxy_url="socks5://reserve",
            checker=checker,
        )

        self.assertEqual(selected, "socks5://reserve")

    def test_select_uses_reserve_when_only_reserve_configured(self):
        selected = select_telegram_proxy(
            bot_token="token",
            primary_proxy_url="",
            reserve_proxy_url="socks5://reserve",
        )

        self.assertEqual(selected, "socks5://reserve")

    def test_select_returns_primary_when_all_preflight_checks_fail(self):
        selected = select_telegram_proxy(
            bot_token="token",
            primary_proxy_url="socks5://primary",
            reserve_proxy_url="socks5://reserve",
            checker=lambda token, proxy, timeout: (False, "fail"),
        )

        self.assertEqual(selected, "socks5://primary")


if __name__ == "__main__":
    unittest.main()
