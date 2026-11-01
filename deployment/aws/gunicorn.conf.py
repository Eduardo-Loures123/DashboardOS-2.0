bind = "unix:/run/dashboardos/app.sock"
workers = 1
worker_class = "sync"
threads = 1
timeout = 120
graceful_timeout = 120
umask = 0o007
accesslog = "-"
errorlog = "-"
capture_output = True
# Evita registrar parâmetros de pesquisa nos logs.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
forwarded_allow_ips = '*'
# Cabeàalhos de proxy são tratados exclusivamente pelo middleware Flask.
secure_scheme_headers = {}
