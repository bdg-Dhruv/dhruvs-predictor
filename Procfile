# IMPORTANT: exactly one worker. Sessions (API keys, watchlists) live in
# this process's memory - a second worker process would have its own,
# separate, empty memory and users would randomly get logged out depending
# on which worker handled their request. --threads gives you concurrency
# without that problem, since threads share the same process memory.
web: gunicorn app:app --workers 1 --threads 8 --timeout 120
