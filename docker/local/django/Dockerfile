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

# RUNTIME STAGE ====================================
FROM base as runtime

# copy built python packages to this image
COPY --from=builder /.venv /.venv
# set venv python as the "default" python
ENV PATH="/.venv/bin:$PATH"

RUN apt-get update \
    # psycopg2 dependencies
    && apt-get install -y libpq-dev \
    # Translations dependencies
    gettext \
    # for testing
    iputils-ping procps \
    # for opening various file formats
    ffmpeg p7zip-full unrar-free file \
    # for downloading megacmd package
    wget

# TODO: remove
# download megacmd (for fetching files from mega.nz)
# ENV EXPECTED_HASH=389c388a068896c7911c4ddfc825b44f587eba8f635dbaf61e4ba30bb83abb13
# RUN wget https://mega.nz/linux/repo/Debian_10.0/amd64/megacmd-Debian_10.0_amd64.deb \
#     # checksum
#     && test "$EXPECTED_HASH" = "$(sha256sum megacmd-Debian_10.0_amd64.deb | awk '{print $1}')" \
#     # install
#     && apt-get install -y ./megacmd-Debian_10.0_amd64.deb \
#     # remove downloaded .deb file
#     && rm ./megacmd-Debian_10.0_amd64.deb \
#     # set setuid bit (mega-cmd-server requires root privileges)
#     && chmod u+s $(which mega-cmd-server)

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
