"""Tests for the SQL Tool executing queries against the SQLite database."""

from pathlib import Path
import pytest
from app.tools.sql_tool import query_database


class TestSQLTool:
    """Verifies functional query execution, row capping, and path leak prevention."""

    def test_query_customers_table(self, test_db: Path):
        res = query_database("SELECT id, name, region FROM customers LIMIT 5", db_path=test_db)
        assert res["success"] is True
        assert len(res["rows"]) == 5
        assert "name" in res["columns"]
        assert "region" in res["columns"]
        assert res["execution_time_ms"] > 0

    def test_query_aggregation_sales(self, test_db: Path):
        res = query_database(
            "SELECT count(*) as total_orders, sum(total_amount) as total_revenue FROM orders",
            db_path=test_db,
        )
        assert res["success"] is True
        assert len(res["rows"]) == 1
        assert res["rows"][0]["total_orders"] > 0
        assert res["rows"][0]["total_revenue"] > 0

    def test_row_limit_enforced(self, test_db: Path):
        # Query requesting up to 10 rows with max_rows cap = 3
        res = query_database("SELECT * FROM customers", db_path=test_db, max_rows=3)
        assert res["success"] is True
        assert len(res["rows"]) == 3
        assert res["row_count"] == 3
        assert res["truncated"] is True
        assert "truncated" in res.get("note", "").lower()

    def test_missing_table_handled_without_path_leak(self, test_db: Path):
        res = query_database("SELECT * FROM non_existent_secret_table", db_path=test_db)
        assert res["success"] is False
        assert "no such table" in res["error"]
        # Ensure absolute filesystem paths are not leaked in error message
        assert str(test_db) not in res["error"]

    def test_rejected_mutation_query(self, test_db: Path):
        res = query_database("DELETE FROM customers WHERE id = 1", db_path=test_db)
        assert res["success"] is False
        assert "Only read-only SELECT queries are permitted" in res["error"]

    def test_empty_query(self, test_db: Path):
        res = query_database("", db_path=test_db)
        assert res["success"] is False
        assert "empty" in res["error"].lower()
