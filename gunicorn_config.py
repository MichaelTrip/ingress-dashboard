# Gunicorn config variables
loglevel = "info"
errorlog = "-"  # stderr
accesslog = "-"  # stdout
worker_tmp_dir = "/dev/shm"
bind = "0.0.0.0:5000"
# Socket.IO sessions and background updates share one process.
workers = 1
worker_class = "gthread"
threads = 100
timeout = 120
keepalive = 5
