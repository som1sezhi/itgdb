FROM python:3.10-slim-buster as base

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# BUILD STAGE ====================================
FROM base as builder

ENV PIPENV_VENV_IN_PROJECT=1

RUN apt-get update \
  # dependencies for building Python packages
  && apt-get install -y build-essential \
  # psycopg2 dependencies
  libpq-dev \
  # Translations dependencies
  gettext

RUN pip install pipenv

# install python packages in /.venv
COPY Pipfile Pipfile.lock /
WORKDIR /
RUN pipenv install --deploy --ignore-pipfile

# CHART-VIEWER BUILD STAGE ====================================
FROM node:22-bullseye-slim as vite-builder

RUN mkdir -p /app/node_modules
WORKDIR /app
COPY ./chart-viewer/package*.json ./
RUN npm ci
COPY ./chart-viewer ./
RUN npm run build

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
    iputils-ping curl \
    # for opening various file formats
    ffmpeg p7zip-full unrar file \
    # for mimetype guessing
    mime-support \
    # cleaning up unused files
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

COPY ./docker/prod/django/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//g' /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY ./docker/prod/django/start.sh /start.sh
RUN sed -i 's/\r$//g' /start.sh
RUN chmod +x /start.sh

COPY ./docker/prod/django/start-celeryworker.sh /start-celeryworker.sh
RUN sed -i 's/\r$//g' /start-celeryworker.sh
RUN chmod +x /start-celeryworker.sh

COPY . /app/
RUN mkdir /app/uploads

RUN mkdir -p /app/chart-viewer/dist
COPY --from=vite-builder /app/dist /app/chart-viewer/dist

RUN useradd -m djangouser

RUN chown -R djangouser /app

USER djangouser

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
