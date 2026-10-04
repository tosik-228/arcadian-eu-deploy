bind = '0.0.0.0:8055'
workers = 2
threads = 1
timeout = 90
graceful_timeout = 30
max_requests = 500
max_requests_jitter = 50
limit_request_line = 4094
limit_request_fields = 40
limit_request_field_size = 8190
accesslog = '-'
errorlog = '-'
import os
control_socket = os.environ.get('GUNICORN_CONTROL_SOCKET', '/tmp/arcadian-gunicorn.sock')
