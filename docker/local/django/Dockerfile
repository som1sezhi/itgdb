FROM python:3.10-slim-bullseye as base

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# if this is not done, some apt-get package fetches will fail with
# Undetermined Error for some reason
# https://github.com/docker/for-mac/issues/6030#issuecomment-1754208413
# ^ this is technically for a different error message but this fix seems to
# work regardless
RUN sed -i 's/http/https/' /etc/apt/sources.list

# BUILD STAGE ====================================
FROM base as builder

RUN apt-get update \
  # dependencies for building Python packages
  && apt-get install -y build-essential \
  # psycopg2 dependencies
  libpq-dev \
  # Translations dependencies
  gettext

# obtain a pre-built uv
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /uvx /bin/

WORKDIR /

# install dependencies (creates a /.venv directory)
RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project


# RUNTIME STAGE ====================================
FROM base as runtime

# copy built python packages to this image
COPY --from=builder /.venv /.venv
# set venv python as the "default" python
ENV PATH="/.venv/bin:$PATH"

# add nonfree repo section to sources (for unrar)
RUN sed -i 's/$/ contrib non-free/' /etc/apt/sources.list

RUN apt-get update \
    # psycopg2 dependencies
    && apt-get install -y libpq-dev \
    # Translations dependencies
    gettext \
    # for testing
    iputils-ping procps strace \
    # for opening various file formats
    ffmpeg p7zip-full unrar file \
    # for mimetype guessing
    mime-support

# cleaning up unused files
RUN apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

COPY ./docker/local/django/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//g' /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY ./docker/local/django/start.sh /start.sh
RUN sed -i 's/\r$//g' /start.sh
RUN chmod +x /start.sh

COPY ./docker/local/django/start-celeryworker.sh /start-celeryworker.sh
RUN sed -i 's/\r$//g' /start-celeryworker.sh
RUN chmod +x /start-celeryworker.sh

COPY . /app/

RUN useradd -m djangouser
USER djangouser

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
