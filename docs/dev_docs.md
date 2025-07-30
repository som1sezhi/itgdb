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

You will need a server (with Docker installed), domain name, S3-compatible
bucket, and GitHub account. You will need to fork this repository onto
your own account.

### Server setup

On the server, clone your repository to `~/itgdb`. Then copy the following files
to the following filenames:

- `.env.example` → `.env`
- `.env.proxy-companion.example` → `.env.proxy-companion`
- `.env.vhost.example` → `.env.vhost`

Change the values within these files as appropriate (fill in domain name,
bucket credentials, etc.). Make sure to set `DEBUG` to 0.

~~Then, log into GitHub Container Registry on the server so Docker can pull
the Django container image during the deployment process:~~ This is no longer needed, as the GitHub Action should now log in automatically.

```shell
docker login https://ghcr.io
# Login with GitHub username and personal access token
```

### Deployment setup

This project uses GitHub Actions to automate deployment. In order for the
workflow to function, the following repository secrets need to be set:

- `CR_PAT`: a Personal Access Token with `write:packages` perms
- `CR_PAT_READ`: a Personal Access Token with `read:packages` perms
- `SSH_HOST`: your server
- `SSH_USERNAME`: the user to log into the server as
- `SSH_PRIVATE_KEY`: the private key to use for the login ([instructions for setting up the SSH key pair](https://github.com/appleboy/ssh-action?tab=readme-ov-file#setting-up-a-ssh-key))

## Production deployment

### Automatic deployment

If everything is set up correctly, pushing to `master` will start the deployment
workflow. This workflow is comprised of two stages:
- Build and upload the Django Docker container image to GitHub Container Registry
- SSH into the server and run Docker Compose

### Manual deployment

You can manually run the deployment workflow via the `workflow_dispatch` event
trigger. On GitHub, go to the Actions tab, click the name of the workflow on the
left sidebar, and then click the Run Workflow button.

If you do not wish to build and upload the Django container, you can run the
Docker Compose commands on the server manually:

```shell
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

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