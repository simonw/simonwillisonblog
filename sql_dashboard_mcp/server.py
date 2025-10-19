"""
MCP Server providing read-only SQL access to PostgreSQL database.

This server integrates with Django SQL Dashboard to provide safe,
read-only SQL query capabilities through the Model Context Protocol.
"""
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import django
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent


# Initialize Django
def setup_django():
    """Setup Django environment."""
    # Add the parent directory to the path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Setup Django settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()


# Create MCP server
mcp = FastMCP("Django SQL Dashboard - Read-only SQL")


def get_db_connection():
    """Get a read-only database connection."""
    from django.db import connection

    # Set connection to read-only mode
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        cursor.execute("SET statement_timeout = '30s'")  # 30 second timeout

    return connection


def execute_readonly_query(sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Execute a read-only SQL query safely.

    Args:
        sql: SQL query to execute
        params: Optional query parameters

    Returns:
        Dictionary containing columns and rows

    Raises:
        ValueError: If query is not a SELECT statement
        Exception: For any database errors
    """
    # Basic validation - ensure it's a SELECT query
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith('SELECT') and not sql_upper.startswith('WITH'):
        raise ValueError("Only SELECT queries are allowed")

    # Additional check for dangerous keywords
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'GRANT', 'REVOKE']
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            raise ValueError(f"Query contains forbidden keyword: {keyword}")

    from django.db import connection

    try:
        with connection.cursor() as cursor:
            # Ensure read-only transaction
            cursor.execute("BEGIN TRANSACTION READ ONLY")

            try:
                # Execute the query
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)

                # Get column names
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                # Fetch results
                rows = cursor.fetchall()

                # Commit the read-only transaction
                cursor.execute("COMMIT")

                return {
                    "columns": columns,
                    "rows": [list(row) for row in rows],
                    "row_count": len(rows)
                }
            except Exception as e:
                cursor.execute("ROLLBACK")
                raise

    except Exception as e:
        return {
            "error": str(e),
            "columns": [],
            "rows": [],
            "row_count": 0
        }


@mcp.tool()
def list_tables(schema: str = "public") -> str:
    """
    List all tables in the specified schema.

    Args:
        schema: Database schema name (default: public)

    Returns:
        Formatted list of tables with their descriptions
    """
    setup_django()

    sql = """
        SELECT
            table_name,
            (SELECT pg_catalog.obj_description(c.oid)
             FROM pg_catalog.pg_class c
             WHERE c.relname = t.table_name
             AND c.relkind = 'r') as description
        FROM information_schema.tables t
        WHERE table_schema = %s
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """

    result = execute_readonly_query(sql, [schema])

    if "error" in result:
        return f"Error: {result['error']}"

    if not result["rows"]:
        return f"No tables found in schema '{schema}'"

    output = [f"Tables in schema '{schema}':\n"]
    for row in result["rows"]:
        table_name = row[0]
        description = row[1] or "No description"
        output.append(f"  - {table_name}: {description}")

    return "\n".join(output)


@mcp.tool()
def describe_table(table_name: str, schema: str = "public") -> str:
    """
    Get detailed information about a table's structure.

    Args:
        table_name: Name of the table
        schema: Database schema name (default: public)

    Returns:
        Formatted table schema with column details
    """
    setup_django()

    sql = """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = %s
        AND table_name = %s
        ORDER BY ordinal_position
    """

    result = execute_readonly_query(sql, [schema, table_name])

    if "error" in result:
        return f"Error: {result['error']}"

    if not result["rows"]:
        return f"Table '{schema}.{table_name}' not found"

    output = [f"Table: {schema}.{table_name}\n"]
    output.append("Columns:")

    for row in result["rows"]:
        col_name, data_type, max_length, nullable, default = row

        type_str = data_type
        if max_length:
            type_str += f"({max_length})"

        null_str = "NULL" if nullable == "YES" else "NOT NULL"
        default_str = f" DEFAULT {default}" if default else ""

        output.append(f"  - {col_name}: {type_str} {null_str}{default_str}")

    return "\n".join(output)


@mcp.tool()
def query_database(sql: str) -> str:
    """
    Execute a read-only SQL query against the database.

    Args:
        sql: SELECT query to execute

    Returns:
        Query results formatted as a table

    Note:
        Only SELECT and WITH queries are allowed.
        Queries have a 30-second timeout.
    """
    setup_django()

    result = execute_readonly_query(sql)

    if "error" in result:
        return f"Error executing query: {result['error']}"

    if not result["rows"]:
        return "Query returned no results"

    # Format results as a table
    columns = result["columns"]
    rows = result["rows"]

    # Calculate column widths
    col_widths = [len(col) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    # Build output
    output = []

    # Header
    header = " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
    separator = "-+-".join("-" * width for width in col_widths)

    output.append(header)
    output.append(separator)

    # Rows (limit to first 100 for display)
    display_rows = rows[:100]
    for row in display_rows:
        row_str = " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        output.append(row_str)

    if len(rows) > 100:
        output.append(f"\n... and {len(rows) - 100} more rows")

    output.append(f"\nTotal rows: {result['row_count']}")

    return "\n".join(output)


@mcp.tool()
def get_table_sample(table_name: str, schema: str = "public", limit: int = 10) -> str:
    """
    Get a sample of rows from a table.

    Args:
        table_name: Name of the table
        schema: Database schema name (default: public)
        limit: Number of rows to return (default: 10, max: 100)

    Returns:
        Sample rows formatted as a table
    """
    setup_django()

    # Sanitize inputs
    if limit > 100:
        limit = 100

    # Build query - using parameterized queries where possible
    # Table names can't be parameterized, so we validate them
    if not table_name.replace('_', '').isalnum():
        return "Error: Invalid table name"
    if not schema.replace('_', '').isalnum():
        return "Error: Invalid schema name"

    sql = f'SELECT * FROM "{schema}"."{table_name}" LIMIT %s'

    result = execute_readonly_query(sql, [limit])

    if "error" in result:
        return f"Error: {result['error']}"

    if not result["rows"]:
        return f"Table '{schema}.{table_name}' is empty"

    # Format results
    columns = result["columns"]
    rows = result["rows"]

    col_widths = [len(col) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    output = []
    header = " | ".join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
    separator = "-+-".join("-" * width for width in col_widths)

    output.append(f"Sample from {schema}.{table_name}:\n")
    output.append(header)
    output.append(separator)

    for row in rows:
        row_str = " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        output.append(row_str)

    return "\n".join(output)


def main():
    """Run the MCP server."""
    setup_django()
    mcp.run()


if __name__ == "__main__":
    main()
