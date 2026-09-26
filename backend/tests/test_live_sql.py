import unittest

from app.services.live_database import validate_sql


class GovernedSqlTests(unittest.TestCase):
    allowed = ["curated.tlc_daily"]

    def test_select_on_allowlisted_table(self):
        sql = validate_sql(
            "SELECT pickup_date, COUNT(*) FROM curated.tlc_daily GROUP BY pickup_date",
            self.allowed,
        )
        self.assertIn("curated.tlc_daily", sql)

    def test_rejects_writes_and_other_tables(self):
        cases = [
            "DELETE FROM curated.tlc_daily",
            "DROP TABLE curated.tlc_daily",
            "SELECT * FROM pg_catalog.pg_tables",
            "SELECT * FROM curated.tlc_daily; DELETE FROM curated.tlc_daily",
            "WITH x AS (DELETE FROM curated.tlc_daily RETURNING *) SELECT * FROM x",
            "SELECT pg_sleep(1) FROM curated.tlc_daily",
        ]
        for sql in cases:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_sql(sql, self.allowed)


if __name__ == "__main__":
    unittest.main()
