"""
Django management command to run the MCP server for read-only SQL access.
"""
from django.core.management.base import BaseCommand
from sql_dashboard_mcp.server import main


class Command(BaseCommand):
    help = 'Run the MCP server for read-only SQL access to the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            type=str,
            default='localhost',
            help='Host to bind the server to (default: localhost)'
        )
        parser.add_argument(
            '--port',
            type=int,
            default=8765,
            help='Port to bind the server to (default: 8765)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting MCP server for read-only SQL access...'))
        self.stdout.write(f"Server will be available for MCP clients")
        self.stdout.write(f"Read-only SQL queries are enforced at the database level")

        try:
            main()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nMCP server stopped'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error running MCP server: {e}'))
            raise
