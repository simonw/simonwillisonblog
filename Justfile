export DATABASE_URL := "postgres:///simonwillisonblog"

uv_run := "uv run --with-requirements requirements.txt"

# Run tests
@default: test

# Run tracked apps' tests (e.g. just test -k test_homepage)
@test *options:
  {{uv_run}} ./manage.py check
  {{uv_run}} pytest {{options}}

# Run development server (e.g. just server 8001)
@server *options:
  DJANGO_DEBUG=1 {{uv_run}} ./manage.py runserver {{options}}

# Run management commands
@manage *options:
  {{uv_run}} ./manage.py {{options}}
