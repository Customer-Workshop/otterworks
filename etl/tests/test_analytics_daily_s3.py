# Regression test for SonarCloud python:S7608 -- S3 writes must verify bucket ownership.
# Parses analytics_daily.py so the check needs no AWS credentials or ETL runtime deps.

import ast
import os
import unittest

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "analytics_daily.py",
)

S3_WRITE_METHODS = {"put_object", "copy_object", "delete_object", "upload_part"}


def s3_write_calls(tree):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in S3_WRITE_METHODS
        ):
            yield node


class ExpectedBucketOwnerTest(unittest.TestCase):
    def setUp(self):
        with open(SCRIPT_PATH, encoding="utf-8") as fh:
            self.tree = ast.parse(fh.read(), filename=SCRIPT_PATH)

    def test_s3_writes_specify_expected_bucket_owner(self):
        calls = list(s3_write_calls(self.tree))
        self.assertTrue(calls, "expected at least one S3 write call in analytics_daily.py")
        for call in calls:
            kwargs = {kw.arg for kw in call.keywords}
            self.assertIn(
                "ExpectedBucketOwner",
                kwargs,
                f"{call.func.attr} at line {call.lineno} must pass ExpectedBucketOwner",
            )

    def test_expected_bucket_owner_comes_from_config(self):
        for call in s3_write_calls(self.tree):
            owner = next(kw.value for kw in call.keywords if kw.arg == "ExpectedBucketOwner")
            self.assertIsInstance(
                owner,
                ast.Name,
                f"ExpectedBucketOwner at line {call.lineno} must be a configured value, not a literal",
            )
            self.assertEqual("aws_account_id", owner.id)


if __name__ == "__main__":
    unittest.main()
