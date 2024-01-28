Start up Redis server:

```shell
redis-server --port 6380
```

Start up Celery worker:

```shell
python -m celery -A itgdb worker -l info
```