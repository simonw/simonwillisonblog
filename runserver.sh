#!/bin/bash
DJANGO_DEBUG=1 \
  uv run --with-requirements requirements.txt \
    python ./manage.py runserver 0.0.0.0:8033
