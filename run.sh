#!/bin/bash

# This script runs the url-catcher in a virtual environment with temporarily
# installed required external Python libraries.
set -e

DIR_ENV=.temp_env

pyvenv $DIR_ENV 
source $DIR_ENV/bin/activate
pip install -r requirements.txt
echo
set +e
uwsgi --socket 127.0.0.1:3031 --wsgi-file url_catcher.py 
set -e
deactivate
rm -rf $DIR_ENV 
