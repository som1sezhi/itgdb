import json
from channels.generic.websocket import WebsocketConsumer
from celery.result import AsyncResult
from asgiref.sync import async_to_sync


class ProgressConsumer(WebsocketConsumer):
    def connect(self):
        if self.scope['user'].is_superuser:
            # set of task IDs this consumer will track
            # (to be supplied by client)
            self.task_ids = set()

            self.accept()
        else:
            self.close()

    def disconnect(self, close_code):
        for task_id in self.task_ids:
            async_to_sync(self.channel_layer.group_discard)(
                task_id, self.channel_name
            )

    def receive(self, text_data):
        # receive initial list of task IDs to track
        task_ids = json.loads(text_data)
        response = []

        for task_id in task_ids:
            result = AsyncResult(task_id)
            state = result.state
            if state == 'PROGRESS':
                # in this case, we can assume result.info is a dict with our
                # progress info inside
                progress = result.info['progress']
                message = result.info['message']
            elif state == 'SUCCESS':
                progress = 1
                message = f'Success! {result.info}'
            elif state == 'FAILURE':
                progress = 1
                message = f'Failure: {result.info}'
            else:
                progress = 0
                message = 'Waiting...'
            response.append({
                'id': task_id,
                'state': state,
                'progress': progress,
                'message': message,
            })

        self.send(text_data=json.dumps(response))

        # only subscribe to groups after sending initial statuses to client
        for task_id in task_ids:
            async_to_sync(self.channel_layer.group_add)(
                task_id, self.channel_name
            )
            self.task_ids.add(task_id)

    def progress_update(self, event):
        # we received a progress update from a task, time to send that update
        # to the client
        data = event['data']
        self.send(text_data=json.dumps([data]))
