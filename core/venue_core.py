# import mtak first since this messes up logging
import logging
logger = logging.getLogger(__name__)

import os
import stat
import redis
import tailer
import json
import hashlib
import psutil
import signal
import uuid
import tarfile
import glob
from datetime import datetime
import subprocess
import time

from .core_utils import get_env

CUSTOM_SCRIPT_LOG_PATH_BASE='/tmp/cs'

_custom_script_base_dir = get_env('CUSTOM_SCRIPT_BASE_DIR')

def _load_json_with_retry(path: str, max_attempts: int=5, delay: float = 0.1):
  """
  This function will retry the loading of a json file (specifically output.json) in case it is being actively written
  to when the load attempt starts.
  
  """

  attempt = 0
  while attempt < max_attempts:
    try:
      with open(path, 'r') as file:
        data = json.load(file)
        return data
    except json.JSONDecodeError as er:
      msg = f"JSON decode failed on attempt {attempt+1}/{max_attempts} for {path}: {er} - retrying"
      logger.debug(msg)
    attempt+=1
    time.sleep(delay * (2*attempt))
  raise RuntimeError(f"unable to read a consistent JSON file from {path}")

def get_current_datetime_stamp():

  # get current time
  now_time = datetime.now()
  formatted_time = now_time.strftime('%Y-%m-%dT%H%M%S')

  return formatted_time


def create_temp_dir_and_logfiles():

  # see if /tmp/cs exists, if not make the base path
  if os.path.isdir(CUSTOM_SCRIPT_LOG_PATH_BASE) is False:
    # open permissions on the base dir so that multiple application users can read/write to it/make tars
    os.makedirs(CUSTOM_SCRIPT_LOG_PATH_BASE)    
    os.chmod(CUSTOM_SCRIPT_LOG_PATH_BASE, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)

  # create a unique session (script) id. This is the script_run_id
  script_run_id = str(uuid.uuid4())
  # get current time
  formatted_time = get_current_datetime_stamp()

  datetime_script_run_id = f'{formatted_time}-{script_run_id}'

  # example path: "/tmp/cs/datetime-uuid/"
  subfolder_with_datetime_and_uuid = os.path.join(CUSTOM_SCRIPT_LOG_PATH_BASE, datetime_script_run_id)
  logger.debug(f'Subfolder with datetime stamp and ID: {subfolder_with_datetime_and_uuid}')

  # dir doesn't exists so create it 
  os.makedirs(subfolder_with_datetime_and_uuid)

  return subfolder_with_datetime_and_uuid, script_run_id


def tar_custom_script_log_files(temp_dir, script_run_id):

  '''
  This function will create a tar package of the input.json, output.json, and script.log files. 
  Each tar will be datestamped with the time the tar was created and the uuid. 

  example tar created in the script temp dir: `/tmp/cs/uuid.tar.gz`

  '''
  tar_full_path = os.path.join(CUSTOM_SCRIPT_LOG_PATH_BASE, script_run_id + '.tar.gz')
  logger.debug(f'Full tar path: {tar_full_path}') 

  with tarfile.open(tar_full_path, 'w:gz') as tar_handle:
    for file_name in glob.glob(os.path.join(temp_dir, '*')):
        isolated_file_name = os.path.basename(file_name)
        logger.debug(f'File found in temp dir: {isolated_file_name}')
        logger.debug(f'Storing in tar: {os.path.join(script_run_id, isolated_file_name)}')
        tar_handle.add(file_name, arcname=os.path.join(script_run_id, isolated_file_name))

  return tar_full_path


def initialize_input_output_and_log_files(subdir, inputs, outputs, script_run_id):

  # create input file 
  input_file_path = os.path.join(subdir, 'input.json')

  with open(input_file_path, 'w') as infile:
    json.dump(inputs, infile)

  # create output file
  output_file_path = os.path.join(subdir, 'output.json')

  with open(output_file_path, 'w') as outfile:
    json.dump(outputs, outfile)

  # create main log file
  script_log_file_path = os.path.join(subdir, 'script.log')

  # logfile_url produces url in convention: "custom_scripts/<script_run_id>/files"
  logfile_url = '/'.join(['custom_script', script_run_id, 'files'])

  return input_file_path, output_file_path, script_log_file_path, logfile_url


def launch_script(path_to_script, inputs, outputs):
  
  # create the temp dir for the custom script files, returns the temp dir and the uuid (to be used later)
  custom_script_temp_dir, script_run_id= create_temp_dir_and_logfiles()
  input_file_path, output_file_path, script_log_file_path, logfile_url = \
    initialize_input_output_and_log_files(custom_script_temp_dir, inputs, outputs, script_run_id)

  logger.debug(f'Input file: {input_file_path}')
  logger.debug(f'Output file: {output_file_path}')
  logger.debug(f'Log file: {script_log_file_path}')
  logger.debug(f'Script run id: {script_run_id}')
  logger.debug(f'Logfile url: {logfile_url}')

  # open a script log file with no buffering
  # Python2:
  #     buffering=0 is available regardless of text or binary file
  # Python3:
  #     buffering=0 is available only for binary file 
  # 
  # Note that script_log_file_path file is opened in binary mode to be compatible with Python2 and Python3.
  # In Python3, since the file is opened as binary, if stdout.write('abc') is used in the sub-process, 
  # it would give a TypeError: a bytes-like object is required, not 'str',
  # But since the file is used for redirection of stdout/stderr, it seems to work fine for Python3.
  log_file = open(script_log_file_path, 'wb', buffering=0)
  
  # disable buffering of stdout/stderr of the subprocess by setting PYTHONUNBUFFERED
  script_env = os.environ.copy()
  script_env['PYTHONUNBUFFERED'] = 'YES'  
 
  process = subprocess.Popen([path_to_script, input_file_path, output_file_path], 
    preexec_fn=os.setsid, env=script_env, stdout=log_file, stderr=log_file)
  process_pid = process.pid

  r = redis.Redis(host='localhost', port=6379, db=0)

  process_redis_data = {
    'process_id': str(process_pid),
    'output_path': output_file_path,
    'logfile_path': script_log_file_path,
    'logfile_url': logfile_url,
    'custom_script_temp_dir': custom_script_temp_dir
  }

  logger.debug(f'Stored redis data: {process_redis_data}')
  r.set(str(script_run_id), json.dumps(process_redis_data))

  return script_run_id


def get_script_log_lines(log_file_path):

  log_lines_list = []

  last_lines = tailer.tail(open(log_file_path), 25)

  for l in last_lines:
    # remove the pesky "/n" at the end of each log line
    log_lines_list.append(l.rstrip('\n'))
  
  return log_lines_list


def check_script_hash(joined_path, script_hash):

  valid_hash = False

  # check hash. return error if hashes do not match 
  BLOCK_SIZE = 65536
  generated_hash = hashlib.sha256()
  with open(joined_path, 'rb') as f:
    fb = f.read(BLOCK_SIZE) # Read from the file. Take in the amount declared above
    while len(fb) > 0: # While there is still data being read from the file
        generated_hash.update(fb) # Update the hash
        fb = f.read(BLOCK_SIZE) # Read the next block from the file

  if generated_hash.hexdigest() == script_hash:
    valid_hash = True

  return valid_hash, script_hash, generated_hash.hexdigest()


def start_custom_script(script_hash, script_path, inputs, outputs): 

  logger.info(f'Starting custom script: {script_path}')

  # join absolute and relative paths together 
  # absolute path needs to be sourced from environment variable set on the config file
  base_path = _custom_script_base_dir
  relative_path_to_base_path = script_path
  raw_joined_path = os.path.join(base_path, relative_path_to_base_path)
  joined_path = os.path.normpath(raw_joined_path)
  logger.debug(f'Joined custom scripts path: {joined_path}')

  # if file does not exist return error 
  if os.path.isfile(joined_path) is False:
    raise Exception(f'Custom script cannot be found: {joined_path}')
  
  # check hash
  try: 
    valid_hash, script_hash, generated_hash = check_script_hash(joined_path, script_hash)
  except Exception as ex:
    raise Exception(f'Failed to check script hash') from ex

  if valid_hash is False:
    msg = f'File hash input ({script_hash}) did not match the file hash: {generated_hash}'
    raise Exception(msg)
  else:
    msg = "File hash matches generated file hash"
    logger.debug(msg)

  try:
    script_run_id = launch_script(joined_path, inputs, outputs)
  except Exception as ex:
    raise Exception(f'Failed to launch script') from ex
  
  logger.debug(f'Script ID generated: {script_run_id}')

  return {'scriptRunId': script_run_id}


def construct_script_outputs(output_json):

  logger.debug(f'Output json: {output_json}')

  structure = {}

  if output_json.get('inputs'):
    structure['inputs'] = output_json['inputs']

  # parse output - object
  if output_json.get('outputs'):
    structure['outputs'] = output_json['outputs']

  # parse output_array - list
  if output_json.get('output_array'):
    structure['output_array'] = output_json['output_array']

  # cycle through entries and extract entry_outputs and entry_output_array
  if output_json.get('entries'):

    structure['entries'] = []
    for entry in output_json['entries']:
      entry_structure = {}
      
      entry_structure['verification_status'] = entry.get('verification_status')

      if entry.get('entry_inputs'):
        entry_structure['entry_inputs'] = entry['entry_inputs']

      if entry.get('entry_output_array'):
        entry_structure['entry_output_array'] = entry['entry_output_array']
      
      if entry.get('entry_outputs'):
        entry_structure['entry_outputs'] = entry['entry_outputs']

      structure['entries'].append(entry_structure)

    if output_json.get('output_summary'):
        structure['output_summary'] = output_json['output_summary']

  return structure


def get_script_status_dict(outputs, script_status, logfile_path, logfile_lines, logfile_url):
  return {
      "custom_script_outputs": outputs,
      "custom_script_status": script_status,
      "logfile_path": logfile_path,
      "logfile_lines": logfile_lines,
      "logfile_url": logfile_url
  }


def get_custom_script_status(script_run_id):

  logger.debug(f'Getting the custom script status for script_run_id: {script_run_id}')

  # get script information via script ID from Redis
  r = redis.Redis(host='localhost', port=6379, db=0)

  try:
    script_info_redis = json.loads(r.get(script_run_id))
  except Exception as ex:
    msg = f'The script run id ({script_run_id}) was not found in REDIS records. Exception: {ex}'
    logger.error(msg)
    raise Exception(msg)

  logger.debug(f'SCRIPT_INFO FROM REDIS: {script_info_redis}')

  # extract PID and see if it's still running 
  pid = script_info_redis.get('process_id') 
  logfile_path = script_info_redis.get('logfile_path')
  output_dir = script_info_redis.get('output_path')
  logfile_url = script_info_redis.get('logfile_url')

  if pid is None:
    msg = f'PID could not be found for script run id ({script_run_id}) in Redis. Check the logs: {logfile_path}'
    logger.error(msg)
    raise Exception(msg)

  # use os.kill to figure out if pid is still running
  pid_is_alive = None

  # preserve current method of checking if pid exists (which means the CS process is still running)
  try:
    os.kill(int(pid), 0)
  except OSError:
    # if the process does not exist, the CS process has ended nominally
    pid_is_alive = False
    logger.debug(f'PID: {pid} is DEAD')
  else:
    # if the process still exists we need to branch the logic to determine if the pid is a zombie process or if it is truly still running
    p = psutil.Process(int(pid))
    # useful pid process status logging
    pid_status_msg = f'PID status: {p.status()}'
    logger.debug(pid_status_msg)
    if p.status() == psutil.STATUS_ZOMBIE:
      msg = f'pid: {pid} is a defunct process'
      logger.debug(msg)
      pid_is_alive = False
    else:
      pid_is_alive = True    

  try:
    output_json = _load_json_with_retry(output_dir, 10, 0.1)
  except Exception as ex:
    msg = f'Error when parsing the script output file. Error: {ex}'
    logger.error(msg)
    raise Exception(msg)


  # extract script status & outputs from output json 
  script_status = output_json.get('custom_script_status')
  if script_status is None:
    msg = 'custom_script_status field was not found in the output file'
    logger.error(msg)
    raise Exception(msg)
  
  # construct script outputs to be sent back to venue server
  constructed_output_json = construct_script_outputs(output_json)
  
  # extract the log file lines
  logfile_lines = get_script_log_lines(logfile_path)

  # this means that the process is dead
  if script_status == 'PENDING' and pid_is_alive is False:
    script_status = 'ERROR'
    output_json['custom_script_status'] = 'ERROR'

    # need to write to output file so that PENDING CAN BE CHANGED TO ERROR  
    with open(output_dir, 'w') as outfile:
      logger.warning(f'The script exited without setting script_status. Write to output file: {outfile}')
      json.dump(output_json, outfile)

  return get_script_status_dict(constructed_output_json, script_status, logfile_path, logfile_lines, logfile_url)


def halt_custom_script(script_run_id):

  logger.debug(f'Halting custom script for script_run_id: {script_run_id}')

  # get script information via script ID from Redis 
  r = redis.Redis(host='localhost', port=6379, db=0)
  try:
    script_info_redis = json.loads(r.get(script_run_id))
  except Exception as ex:
    msg = f'The script run id (script_run_id) was not found. Cannot halt script: {ex}'
    logger.error(msg)
    raise Exception(msg)

  pid = script_info_redis.get('process_id')

  if pid is None:
    msg = f'PID: {script_run_id} could not be found in Redis'
    logger.error(msg)
    raise Exception(msg)
  else:
    pid = int(pid)

  try:
    os.kill(pid, 0)
  except OSError:
    logger.warning(f'Error when killing a custom script (PID: {pid}). It may have already exited.')
  else:
    logger.debug(f'PID: {pid} was alive, halted main process and children processes...')


  # if the process group doesn't exist, it needs to exit gracefully
  try:
    os.killpg(os.getpgid(pid), signal.SIGTERM)
  except:
    logger.warning(f'Error when killing process group for pid: {pid}. The process may not exist any more.')

  # delete script (session) id from Redis (keep Redis clean)
  r.delete(script_run_id)

  return ''


def get_custom_script_files(script_run_id):

  logger.debug(f'Retrieving latest custom script logs and package them into tarball: {script_run_id}')

  #custom_script_temp_dir = os.path.join(CUSTOM_SCRIPT_LOG_PATH_BASE, script_run_id)

  # get script information via script ID from Redis
  r = redis.Redis(host="localhost", port=6379, db=0)

  try:
    script_info_redis = json.loads(r.get(script_run_id))
  except Exception as ex:
    msg = f'The script run id ({script_run_id}) was not found. Error: {ex}'
    logger.error(msg)
    raise Exception(msg)

  logger.debug(f'SCRIPT_INFO FROM REDIS: {script_info_redis}')

  custom_script_temp_dir = script_info_redis.get('custom_script_temp_dir')

  # check if base dir + datetime stamp exists, else return error
  # ex: "/tmp/cs/timestamp-uuid"
  if os.path.exists(custom_script_temp_dir) is False:
    msg = f'Custom script temp dir ({custom_script_temp_dir}) was not found'
    logger.error(msg)
    raise Exception(msg)
  
  try:
    tar_path = tar_custom_script_log_files(temp_dir=custom_script_temp_dir, script_run_id=script_run_id)
    logger.debug(f'Full tar path: {tar_path}')
  except Exception as ex:
    msg = f'There was an error packaging the custom script logs into a tarball: {ex}'
    logger.error(msg)
    raise Exception(msg)

  return tar_path





