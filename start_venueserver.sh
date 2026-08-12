#!/bin/bash
SCRIPT_FILE=$(realpath $0)
SCRIPT_DIR=$(dirname $SCRIPT_FILE)
VENV_DIR="$SCRIPT_DIR/venv3"

# Set text locale explicitly to avoid error when starting uvicorn
export LC_ALL='en_US.UTF-8'
export LANG='en_US.UTF-8'

usage() {
  echo "
  Usage: $0 -p PORT -f ENV_FILE [-v VENV_DIR]
  
    Options:
      -p PORT (required): port used by VenueServer
      -f ENV_FILE: path to a file that defines environment variables (required)
      -v VENV_DIR (optional): path to Python virtual environment (default: $SCRIPT_DIR/venv3)

  Example:
    $0 -p 19443 -f config/venueserver_dev_envs.sh
    $0 -p 19443 -f config/venueserver_dev_envs.sh -v /home/user/my-venv
  " 
}

input_error() {
  usage
  exit 1
}

while getopts ":p:f:v:" options; do
  case "${options}" in
    p)                     
      PORT=${OPTARG}
      ;;
    f)                                    
      ENV_FILE=${OPTARG}
      ;;
    v)
      VENV_DIR=${OPTARG}
      ;;
    :)
      echo "Error: -${OPTARG} requires a value."
      input_error
      ;;
    *)                                    
      break
      ;;
  esac
done

if [[ -z "$ENV_FILE" ]] 
then
  input_error
fi

echo "ENV_FILE: $ENV_FILE"

if [[ -f "$ENV_FILE" ]]
then
  source "$ENV_FILE"
else
  echo "Error: file not found. $ENV_FILE"
  exit 1
fi


if [[ -z $PORT ]]
then
    echo "Error: PORT is required."
    input_error
fi

if [ -d "$VENV_DIR" ] 
then
    echo "Use Python virtual env: $VENV_DIR"
    source $VENV_DIR/bin/activate
else
    echo "ERROR: Python virtual env does not exist: $VENV_DIR"
    exit 1
fi

# Change PYTHONPATH to use local packages first.
# Need this to override the system level installation of Click. 
# FASTAPI needs click version >= 7
PYVER=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
export PYTHONPATH=$VENV_DIR/lib/python$PYVER/site-packages:$VENV_DIR/lib64/python$PYVER/site-packages
IFS=':' read -ra PATHS <<< "$PYTHONPATH"
echo "PYTHONPATH"
for i in "${PATHS[@]}"; do
    echo " - $i" 
done

echo "Starting Venue Server on port $PORT"

$VENV_DIR/bin/python $SCRIPT_DIR/main.py --port $PORT
