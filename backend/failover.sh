#!/bin/bash

PRIMARY_HOST="100.123.230.103"
PRIMARY_PORT="5432"
LOCAL_ENV="/home/awais-faiz/Dev/ASH/backend/.env"
LOG="/home/awais-faiz/Dev/ASH/backend/failover.log"

check_primary() {
    pg_isready -h $PRIMARY_HOST -p $PRIMARY_PORT -q
    return $?
}

get_current_host() {
    grep "^DB_HOST" $LOCAL_ENV | cut -d'=' -f2
}

switch_to_local() {
    echo "$(date) — Primary DOWN. Switching to local DB..." >> $LOG
    sed -i 's/^DB_HOST=.*/DB_HOST=localhost/' $LOCAL_ENV
    # Promote local replica to primary
    sudo -u postgres pg_ctlcluster 16 main promote
    echo "$(date) — Switched to local DB successfully." >> $LOG
}

switch_to_primary() {
    echo "$(date) — Primary UP. Switching back to Helsinki DB..." >> $LOG
    sed -i 's/^DB_HOST=.*/DB_HOST=100.123.230.103/' $LOCAL_ENV
    echo "$(date) — Switched back to Helsinki DB successfully." >> $LOG
}

CURRENT_HOST=$(get_current_host)

if check_primary; then
    if [ "$CURRENT_HOST" != "100.123.230.103" ]; then
        switch_to_primary
    fi
else
    if [ "$CURRENT_HOST" != "localhost" ]; then
        switch_to_local
    fi
fi
