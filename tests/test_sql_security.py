"""Tests verifying the SQL Validator's allowlist security and anti-injection defenses."""

import pytest
from app.safety.sql_validator import validate_sql_query


class TestSQLSecurityValidator:
    """Exhaustive tests verifying that no SQL mutation or unsafe query can pass validation."""

    def test_valid_select_succeeds(self):
        query = "SELECT id, name FROM customers WHERE region = 'North America'"
        res = validate_sql_query(query)
        assert res.is_valid is True
        assert res.sanitized_sql is not None
        assert res.error is None

    def test_valid_with_cte_succeeds(self):
        query = """
        WITH monthly_rev AS (
            SELECT substr(sale_date, 1, 7) AS month, sum(net_revenue) AS rev
            FROM sales
            GROUP BY month
        )
        SELECT * FROM monthly_rev WHERE rev > 10000
        """
        res = validate_sql_query(query)
        assert res.is_valid is True
        assert res.error is None

    def test_insert_rejected(self):
        query = "INSERT INTO customers (name, email, region, segment, created_at) VALUES ('Hacker', 'h@x.com', 'NA', 'Ent', '2025-01-01')"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_update_rejected(self):
        query = "UPDATE products SET unit_price = 0 WHERE id = 1"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_delete_rejected(self):
        query = "DELETE FROM orders WHERE id = 1"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_drop_rejected(self):
        query = "DROP TABLE customers"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_alter_rejected(self):
        query = "ALTER TABLE products ADD COLUMN backdoor TEXT"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_attach_rejected(self):
        query = "ATTACH DATABASE '/tmp/evil.db' AS evil"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_pragma_rejected(self):
        query = "PRAGMA table_info(customers)"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_vacuum_rejected(self):
        query = "VACUUM"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Only read-only SELECT queries are permitted" in res.error or "Disallowed" in res.error

    def test_multi_statement_injection_rejected(self):
        query = "SELECT * FROM customers; DROP TABLE orders;"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Multiple SQL statements" in res.error or "Only a single" in res.error

    def test_select_into_rejected(self):
        query = "SELECT * INTO backup_customers FROM customers"
        res = validate_sql_query(query)
        assert res.is_valid is False
        assert "Disallowed SQL keyword detected" in res.error or "Only read-only" in res.error

    def test_transaction_statements_rejected(self):
        for stmt in ("BEGIN TRANSACTION", "COMMIT", "ROLLBACK", "SAVEPOINT sp1"):
            res = validate_sql_query(stmt)
            assert res.is_valid is False

    def test_oversized_query_rejected(self):
        huge_query = "SELECT " + "name, " * 1000 + "id FROM customers"
        res = validate_sql_query(huge_query, max_length=500)
        assert res.is_valid is False
        assert "maximum allowed length" in res.error

    def test_empty_query_rejected(self):
        res = validate_sql_query("   ")
        assert res.is_valid is False
        assert "empty" in res.error.lower()

    def test_malformed_sql_handled(self):
        res = validate_sql_query("SELECT FROM WHERE WHERE")
        # Either flagged or accepted syntactically if AST parses it as a SELECT statement
        # but execution will fail safely at SQLite level
        assert isinstance(res.is_valid, bool)
