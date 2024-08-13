#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

python manage.py collectstatic --noinput
python manage.py migrate --noinput
daphne -b 0.0.0.0 -p 8000 itgdb.asgi:application