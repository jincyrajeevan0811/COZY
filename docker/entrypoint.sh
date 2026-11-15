#!/bin/sh
set -e

# Wait for the database when using MySQL
if [ "$DB_ENGINE" = "mysql" ]; then
  echo "Waiting for MySQL at $DB_HOST:$DB_PORT..."
  python - <<'PY'
import os, time, MySQLdb
for attempt in range(60):
    try:
        MySQLdb.connect(host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", 3306)),
                        user=os.environ["DB_USER"], passwd=os.environ.get("DB_PASSWORD", ""))
        break
    except Exception:
        time.sleep(2)
PY
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
