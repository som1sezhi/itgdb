#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

python manage.py collectstatic --noinput
python manage.py migrate --noinput
gunicorn itgdb.wsgi:application --bind 0.0.0.0:8000