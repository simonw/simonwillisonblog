# Django SQL Dashboard MCP Server

A Model Context Protocol (MCP) server providing read-only SQL access to PostgreSQL databases through Django SQL Dashboard.

## Overview

This MCP server allows AI assistants (like Claude) to safely query your PostgreSQL database with read-only access. It integrates with Django's database configuration and enforces multiple levels of security to prevent data modification.

## Features

- **Read-only Access**: Enforced at multiple levels:
  - Session-level transaction read-only mode
  - Query validation to block INSERT/UPDATE/DELETE/DROP/etc.
  - PostgreSQL transaction isolation
- **Safe Query Execution**: 30-second statement timeout to prevent long-running queries
- **Schema Exploration**: Tools to list tables and describe table structures
- **Sample Data**: Ability to preview table contents
- **Django Integration**: Uses Django's database configuration

## Installation

1. Add the `mcp` package to your requirements:

```bash
pip install mcp>=1.0.0
```

2. Ensure `django-sql-dashboard` is in your Django INSTALLED_APPS (optional, for additional dashboard features):

```python
# settings.py
INSTALLED_APPS = [
    ...
    'django_sql_dashboard',
    'sql_dashboard_mcp',
]
```

## Usage

### Running the Server

Start the MCP server using the Django management command:

```bash
python manage.py run_mcp_server
```

### Configuration for Claude Desktop

Add this configuration to your Claude Desktop config file (usually at `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "django-sql-dashboard": {
      "command": "python",
      "args": [
        "/path/to/your/project/manage.py",
        "run_mcp_server"
      ],
      "env": {
        "DJANGO_SETTINGS_MODULE": "config.settings"
      }
    }
  }
}
```

Update the path to match your project location.

## Available Tools

The MCP server provides the following tools to AI assistants:

### 1. list_tables

List all tables in a database schema.

**Parameters:**
- `schema` (optional): Database schema name (default: "public")

**Example:**
```
list_tables(schema="public")
```

### 2. describe_table

Get detailed information about a table's structure including columns, data types, and constraints.

**Parameters:**
- `table_name`: Name of the table to describe
- `schema` (optional): Database schema name (default: "public")

**Example:**
```
describe_table(table_name="blog_entry", schema="public")
```

### 3. query_database

Execute a read-only SQL query against the database.

**Parameters:**
- `sql`: SELECT or WITH query to execute

**Example:**
```
query_database(sql="SELECT * FROM blog_entry LIMIT 10")
```

**Restrictions:**
- Only SELECT and WITH queries are allowed
- Queries have a 30-second timeout
- Maximum 100 rows displayed (more are still counted)

### 4. get_table_sample

Get a sample of rows from a table.

**Parameters:**
- `table_name`: Name of the table
- `schema` (optional): Database schema name (default: "public")
- `limit` (optional): Number of rows to return (default: 10, max: 100)

**Example:**
```
get_table_sample(table_name="blog_entry", limit=20)
```

## Security Features

### Read-Only Enforcement

The server enforces read-only access through multiple mechanisms:

1. **PostgreSQL Session Settings**: Each connection sets `TRANSACTION READ ONLY`
2. **Query Validation**: Blocks queries containing forbidden keywords (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE)
3. **Statement Timeout**: 30-second limit on all queries
4. **Transaction Isolation**: Each query runs in its own read-only transaction

### Query Safety

- SQL injection protection through parameterized queries where possible
- Table and schema name validation
- Result set size limits to prevent memory issues

## Integration with Django SQL Dashboard

This MCP server is designed to complement the Django SQL Dashboard package. While Django SQL Dashboard provides a web interface for running SQL queries, this MCP server provides programmatic access for AI assistants.

To use both together, ensure `django-sql-dashboard` is in your `INSTALLED_APPS` and follow the Django SQL Dashboard documentation for web interface setup.

## Troubleshooting

### Connection Issues

If the MCP server can't connect to the database:

1. Verify your Django database settings in `settings.py`
2. Ensure PostgreSQL is running
3. Check database credentials and permissions

### Permission Errors

If you get permission errors when running queries:

1. Ensure the database user has SELECT permissions on the tables
2. Check that the schema exists and is accessible

### Timeout Errors

If queries timeout:

1. The default timeout is 30 seconds
2. Consider optimizing slow queries
3. Add appropriate indexes to improve query performance

## Development

### Project Structure

```
sql_dashboard_mcp/
├── __init__.py
├── server.py                      # Main MCP server implementation
├── management/
│   └── commands/
│       └── run_mcp_server.py     # Django management command
├── README.md                      # This file
└── claude_desktop_config.json    # Example Claude Desktop config
```

### Testing

You can test the server by running it and connecting with Claude Desktop or another MCP client:

```bash
python manage.py run_mcp_server
```

## Patch for django-sql-dashboard

This implementation can be integrated into the django-sql-dashboard package. See `django-sql-dashboard.patch` for the changes that can be applied to add MCP server support to django-sql-dashboard itself.

## License

This code is provided as an extension to django-sql-dashboard and follows the same license.

## Contributing

Contributions are welcome! Please ensure that:

1. Security features remain intact
2. Read-only access is enforced
3. Code follows Django and Python best practices
4. Tests are included for new features

## Credits

- Built on the [Model Context Protocol](https://modelcontextprotocol.io/)
- Integrates with [Django SQL Dashboard](https://github.com/simonw/django-sql-dashboard)
- Inspired by existing PostgreSQL MCP servers
