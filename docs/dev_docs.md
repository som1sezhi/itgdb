## Dev setup

Make a clone of `.env.example` called `.env`, and change the values inside to
your liking (though `AWS_STORAGE_BUCKET_NAME` should be kept as `itgdbtest`).

Then in the project root directory, with Docker (and Docker Compose) installed:

```shell
docker-compose build
docker-compose up -d
```

You may then visit [http://localhost:8000/](http://localhost:8000/) to view
the site.

**Note:** This project uses Pipenv for dependency management. It may be useful
to set up a local Pipenv environment for this project (outside of Docker), if 
only to ease updating the Pipfile if dependencies change.

**Note:** Beware that when the localstack container shuts down, all the files
inside get deleted.

**Note:** In VS Code, after changing `.env`, you may need to restart the
terminal before running docker-compose. The terminal may load the env vars 
from the file into the terminal session, which will be taken in by
docker-compose, potentially ignoring any changes made to `.env` until you 
reload.

## Production setup

You will need a server (with Docker installed), domain name, and S3-compatible
bucket.

Clone the following files to the following filenames:

- `.env.example` → `.env`
- `.env.proxy-companion.example` → `.env.proxy-companion`
- `.env.vhost.example` → `.env.vhost`

Change the values within these files as appropriate (fill in domain name,
bucket credentials, etc.). Make sure to set `DEBUG` to 0.

Then in the project root directory:

```shell
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

## Automating deployment with GitHub Actions

This project uses GitHub Actions to automate deployment to some extent.
The following repository secrets need to be set:

- `CR_PAT`: a Personal Access Token with `read:packages` and `write:packages` perms
- `SSH_HOST`: your server
- `SSH_USERNAME`: the user to log into the server as
- `SSH_PRIVATE_KEY`: the private key to use for the login ([instructions for setting up the SSh key pair](https://github.com/appleboy/ssh-action?tab=readme-ov-file#setting-up-a-ssh-key))

Additionally, as of current, the workflow expects the location of the project
on the remote server to be `~/itgdb`.

## Other commands I found useful in the past

Start up Redis server on port 6380 (sometimes port 6379 is occupied on my
machine):

```shell
redis-server --port 6380
```

Start up Celery worker:

```shell
python -m celery -A itgdb worker -l info
```

Start Localstack:
```shell
localstack start -d
```

Create bucket:
```shell
awslocal s3api create-bucket --bucket itgdbtest
```