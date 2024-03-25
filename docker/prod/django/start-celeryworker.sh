#!/bin/bash

set -o errexit
set -o nounset

python -m celery -A itgdb worker -l info