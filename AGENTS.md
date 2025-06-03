# Repo Guidelines

## Running tests

1. Set the `DATABASE_URL` environment variable to `postgres://testuser:testpass@localhost/simonwillisonblog`.
2. Run tests from the repository root with:

```bash
python manage.py test -v3
```
