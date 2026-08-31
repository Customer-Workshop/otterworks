import configparser
import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch

SCRIPTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
)
sys.path.insert(0, SCRIPTS_PATH)
aws_owner = importlib.import_module("aws_owner")


class ExpectedBucketOwnerResolverTest(unittest.TestCase):
    def test_config_value_wins(self):
        config = configparser.ConfigParser()
        config.read_dict({"aws": {"account_id": "123456789012"}})

        with patch.dict(os.environ, {"AWS_ACCOUNT_ID": ""}), patch.object(aws_owner.boto3, "client") as client:
            self.assertEqual(
                "123456789012",
                aws_owner.resolve_expected_bucket_owner(config, "key", "secret", "region"),
            )

        client.assert_not_called()

    def test_missing_or_blank_config_falls_back_to_environment(self):
        configs = [
            configparser.ConfigParser(),
            configparser.ConfigParser(),
        ]
        configs[1].read_dict({"aws": {"account_id": "   "}})

        for config in configs:
            with self.subTest(config=config), patch.dict(
                os.environ, {"AWS_ACCOUNT_ID": "210987654321"}
            ), patch.object(aws_owner.boto3, "client") as client:
                self.assertEqual(
                    "210987654321",
                    aws_owner.resolve_expected_bucket_owner(config, "key", "secret", "region"),
                )
                client.assert_not_called()

    def test_legacy_config_without_aws_section_reaches_sts(self):
        config = configparser.ConfigParser()
        sts_client = Mock()
        sts_client.get_caller_identity.return_value = {"Account": "210987654321"}

        with patch.dict(os.environ, {"AWS_ACCOUNT_ID": ""}), patch.object(
            aws_owner.boto3, "client", return_value=sts_client
        ) as client:
            aws_owner.resolve_expected_bucket_owner(config, "key", "secret", "region")

        client.assert_called_once_with(
            "sts",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            region_name="region",
        )

    def test_sts_fallback_returns_caller_account(self):
        config = configparser.ConfigParser()
        config.read_dict({"aws": {}})
        sts_client = Mock()
        sts_client.get_caller_identity.return_value = {"Account": "210987654321"}

        with patch.dict(os.environ, {"AWS_ACCOUNT_ID": ""}), patch.object(
            aws_owner.boto3, "client", return_value=sts_client
        ):
            result = aws_owner.resolve_expected_bucket_owner(config, "key", "secret", "region")

        self.assertEqual("210987654321", result)

    def test_all_sources_blank_raise_runtime_error(self):
        config = configparser.ConfigParser()
        sts_client = Mock()
        sts_client.get_caller_identity.return_value = {"Account": ""}

        with patch.dict(os.environ, {"AWS_ACCOUNT_ID": ""}), patch.object(
            aws_owner.boto3, "client", return_value=sts_client
        ), self.assertRaisesRegex(
            RuntimeError,
            "Unable to resolve the expected S3 bucket owner AWS account ID",
        ):
            aws_owner.resolve_expected_bucket_owner(config, "key", "secret", "region")


if __name__ == "__main__":
    unittest.main()
