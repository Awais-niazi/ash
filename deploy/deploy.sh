#!/usr/bin/env bash
#
# Ash server deploy script. Install on the server as /home/awais/deploy.sh:
#   cp /home/awais/ash/deploy/deploy.sh /home/awais/deploy.sh
#   chmod +x /home/awais/deploy.sh
#
# Hardened vs. the original: aborts on ANY failed step (notably a failed
# git pull, which used to be ignored and still printed "success"), uses the
# venv explicitly, and restarts the Celery worker/beat so scheduled-task code
# changes actually take effect.

set -euo pipefail

REPO_DIR="/home/awais/ash"
BACKEND_DIR="$REPO_DIR/backend"
VENV_PY="$BACKEND_DIR/venv/bin/python"
VENV_PIP="$BACKEND_DIR/venv/bin/pip"

echo "🚀 Deploying Ash..."

echo "📦 Pulling latest code..."
git -C "$REPO_DIR" pull --ff-only

echo "📦 Installing dependencies..."
"$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet

echo "🗄️  Running migrations..."
"$VENV_PY" "$BACKEND_DIR/manage.py" migrate --noinput

echo "🔄 Restarting services..."
sudo systemctl restart gunicorn
# Restart the scheduler too, but only if the units are installed, so this
# script still works on a box that hasn't set up Celery yet.
for svc in celery-worker celery-beat; do
    if systemctl list-unit-files "$svc.service" >/dev/null 2>&1 \
       && systemctl is-enabled "$svc" >/dev/null 2>&1; then
        sudo systemctl restart "$svc"
        echo "   restarted $svc"
    fi
done

echo "✅ Checking status..."
systemctl is-active gunicorn >/dev/null && echo "   gunicorn: active" || echo "   gunicorn: NOT active"

echo "🎉 Ash deployed successfully!"
