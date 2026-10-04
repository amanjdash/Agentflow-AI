"""Strict allowlist and AST-based SQL query validator for database safety."""

from __future__ import annotations

import re
from typing import NamedTuple, Optional, Set
import sqlparse
from sqlparse.sql import Statement, Token, TokenList
from sqlparse.tokens import DDL, DML, Keyword

from app.safety.limits import GLOBAL_LIMITS

# Forbidden keywords covering mutations, DDL, transaction controls, and SQLite administrative commands
FORBIDDEN_KEYWORDS: Set[str] = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "REPLACE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "PRAGMA",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE",
    "INTO",
    "UPSERT",
    "MERGE",
    "RENAME",
    "TRUNCATE",
}

# Regex to detect multiple statements separated by semicolon
SEMICOLON_SPLIT_REGEX = re.compile(r";\s*\S+")


class ValidationResult(NamedTuple):
    """Result of validating an SQL query."""
    is_valid: bool
    error: Optional[str] = None
    sanitized_sql: Optional[str] = None


def _contains_forbidden_tokens(token_list: TokenList) -> Optional[str]:
    """Recursively inspects token list for any disallowed DML/DDL or administrative tokens."""
    for token in token_list.tokens:
        if token.is_group:
            err = _contains_forbidden_tokens(token)
            if err:
                return err

        val = token.value.strip().upper()
        # Direct keyword comparison
        if val in FORBIDDEN_KEYWORDS:
            return f"Disallowed SQL keyword detected: '{val}'"

        # Check DDL / DML flags
        if token.ttype in (DDL,):
            return f"DDL operations are strictly forbidden: '{val}'"

        if token.ttype in (DML,) and val not in ("SELECT",):
            return f"Non-SELECT DML operations are strictly forbidden: '{val}'"

    return None


def validate_sql_query(query: str, max_length: int = GLOBAL_LIMITS.max_sql_query_length) -> ValidationResult:
    """Validates that an SQL query is strictly a single, read-only SELECT or safe WITH...SELECT query.

    Enforces:
    1. Maximum query length.
    2. Exactly one executable statement (no statement chaining via semicolon).
    3. Root statement type allowlist: must be SELECT or WITH.
    4. Full AST walk verifying absence of write/DDL/PRAGMA/ATTACH/TRANSACTION keywords.
    """
    if not query or not query.strip():
        return ValidationResult(is_valid=False, error="SQL query cannot be empty.")

    clean_query = query.strip()

    # 1. Enforce length limit
    if len(clean_query) > max_length:
        return ValidationResult(
            is_valid=False,
            error=f"SQL query exceeds maximum allowed length of {max_length} characters.",
        )

    # 2. Reject multi-statement queries containing semicolons followed by commands
    if SEMICOLON_SPLIT_REGEX.search(clean_query):
        return ValidationResult(
            is_valid=False,
            error="Multiple SQL statements in a single query are strictly forbidden.",
        )

    # 3. Parse AST using sqlparse
    try:
        parsed_statements = sqlparse.parse(clean_query)
    except Exception as exc:
        return ValidationResult(is_valid=False, error=f"Malformed SQL syntax: {str(exc)}")

    # Remove empty statements if any
    statements = [s for s in parsed_statements if str(s).strip() and not str(s).strip() == ";"]

    if len(statements) != 1:
        return ValidationResult(
            is_valid=False,
            error="Only a single SQL statement is allowed per execution.",
        )

    statement = statements[0]

    # 4. Verify root statement type
    first_keyword: Optional[Token] = None
    for token in statement.tokens:
        if token.is_whitespace or token.ttype in (sqlparse.tokens.Comment,):
            continue
        first_keyword = token
        break

    if not first_keyword:
        return ValidationResult(is_valid=False, error="Query contains no executable SQL statements.")

    root_keyword = first_keyword.value.strip().upper()
    if root_keyword not in ("SELECT", "WITH"):
        return ValidationResult(
            is_valid=False,
            error=f"Only read-only SELECT queries are permitted. Detected: '{root_keyword}'.",
        )

    # 5. Recursive AST token inspection for forbidden operations
    forbidden_error = _contains_forbidden_tokens(statement)
    if forbidden_error:
        return ValidationResult(is_valid=False, error=forbidden_error)

    # 6. For WITH queries, ensure the terminal statement is a SELECT
    if root_keyword == "WITH":
        has_select = any(
            token.value.strip().upper() == "SELECT"
            for token in statement.flatten()
            if token.ttype in (Keyword, DML)
        )
        if not has_select:
            return ValidationResult(
                is_valid=False,
                error="WITH common table expressions must conclude with a SELECT query.",
            )

    # Strip trailing semicolon for clean execution
    sanitized = clean_query.rstrip(";").strip()
    return ValidationResult(is_valid=True, sanitized_sql=sanitized)
