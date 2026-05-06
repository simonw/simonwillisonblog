#!/bin/bash
DJANGO_DEBUG=1 \
  uv run \
    --with-requirements <(grep -v s3_web_manager_django requirements.txt) \
    --with-editable ~/dev/s3-web-manager-django \
    python ./manage.py runserver 0.0.0.0:8033
