import unittest

from utils.monthly_metrics_config import merge_monthly_metrics_recipients


class MonthlyMetricsDeliveryTests(unittest.TestCase):
    def test_required_recipients_are_appended_without_losing_existing_addresses(self):
        recipients = merge_monthly_metrics_recipients(
            "existing@example.by; FIN@ai-agentix.by"
        )

        self.assertEqual(
            recipients,
            "existing@example.by, FIN@ai-agentix.by, boss@ai-agentix.by, operations@ai-agentix.by",
        )

    def test_empty_configuration_still_contains_required_recipients(self):
        self.assertEqual(
            merge_monthly_metrics_recipients(None),
            "boss@ai-agentix.by, fin@ai-agentix.by, operations@ai-agentix.by",
        )


if __name__ == "__main__":
    unittest.main()
