Start up Redis server:

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

In VS Code, when changing .env, make sure to restart the terminal before running docker-compose.