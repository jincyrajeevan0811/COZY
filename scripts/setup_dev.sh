#!/usr/bin/env bash
# One-time local setup for COZY (Linux / macOS). On Windows run the same commands in PowerShell.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

[ -f .env ] || cp .env.example .env

# Generate migrations for every app (first run only), then create the database.
python manage.py makemigrations accounts categories products inventory cart wishlist coupons shipping \
  orders payments reviews notifications support website_settings dashboard
python manage.py migrate
python manage.py seed_cozy

echo
echo "Now create your Super Admin:  python manage.py createsuperuser"
echo "Then start the server:        python manage.py runserver"
echo "Storefront: http://127.0.0.1:8000/   Dashboard: http://127.0.0.1:8000/cozy-admin/"
