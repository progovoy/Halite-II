#!/usr/bin/env bash

# This script is essentially the second half of the coordinator's startup
# script.

pkill -f -9 SCREEN

virtualenv --python=python3.6 venv

source venv/bin/activate
pip install -r requirements.txt

#wget -O cloud_sql_proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64
#chmod +x ./cloud_sql_proxy

# Get the spec for the DB instance to pass to Cloud SQL Proxy
#DB_INSTANCE="$(python -m apiserver.scripts.print_db_proxy_instance)"

#echo "Running sqlproxy with DB_INSTANCE: ${DB_INSTANCE}"
#screen -S sqlproxy -d -m /bin/bash -c \
#    "./cloud_sql_proxy -instances=${DB_INSTANCE}=tcp:3307"

#echo "Running api server"
#screen -S api -d -m /bin/bash -c \
#    "PYTHONPATH=$(pwd) LC_ALL=C.UTF-8 LANG=C.UTF-8 FLASK_DEBUG=1 FLASK_APP=apiserver.server flask run --with-threads -h 0.0.0.0 -p 5000"

#echo "Running coordinator"
#screen -S coordinator_internal -d -m /bin/bash -c \
#    "PYTHONPATH=$(pwd) FLASK_APP=apiserver.coordinator_server flask run --with-threads -h 0.0.0.0 -p 5001"

echo "Running badge deamon"
screen -S badge_daemon -d -m /bin/bash -c \
    "PYTHONPATH=$(pwd) python3 -m apiserver.scripts.badge_daemon.py"

# Run game deletion job at 8 AM UTC = midnight PST (DOES NOT account
# for DST)
# Disabled after finals ended
# { crontab -l -u worker; echo "0 8 * * * $(pwd)/delete_old_games.sh"; } | crontab -u worker -

#PYTHONPATH=$(pwd) LC_ALL=C.UTF-8 LANG=C.UTF-8 FLASK_DEBUG=1 FLASK_APP=apiserver.server flask run --with-threads -h 0.0.0.0 -p 5000
