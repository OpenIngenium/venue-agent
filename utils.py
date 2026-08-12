import logging
logger = logging.getLogger(__name__)

import os
import jwt
import zlib
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

PUBLIC_PEM_FILE = 'exec_venue_public_pem.pem'
ACCEPTED_SCOPES = ['execute:wsts', 'execute:sit', 'execute:testbed', 'execute:other']

public_pem_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 
                               PUBLIC_PEM_FILE)
exec_venue_public_pem_file = None
exec_venue_public_pem = None
exec_venue_public_pem_barray = None
exec_venue_public_key_object = None
key_crc32 = None

try:
  logger.info(f'Loading public key from: {public_pem_path}')
  exec_venue_public_pem_file = open(public_pem_path, 'r')
  exec_venue_public_pem = exec_venue_public_pem_file.read()
  exec_venue_public_pem_barray = bytearray()
  exec_venue_public_pem_barray.extend(map(ord, exec_venue_public_pem))
  key_crc32 = hex(zlib.crc32(exec_venue_public_pem_barray) & 0xffffffff)
  
  # Load the key as a proper cryptography object for compatibility with newer PyJWT/cryptography versions
  exec_venue_public_key_object = serialization.load_pem_public_key(
    exec_venue_public_pem.encode('utf-8'),
    backend=default_backend()
  )
  
  logger.info(f'public key crc32: {key_crc32}')
  logger.info(f'public key type: {type(exec_venue_public_key_object).__name__}')
except Exception as ex:
  msg = f'Failed to load JWT public key from {public_pem_path}'
  logger.exception(msg)
  raise Exception(msg) from ex

# This function is use to print key info after log file handler is initialized
def print_key_info():
  logger.info(f'Using public key from: {public_pem_path}')
  logger.info(f'public key key_crc32: {key_crc32}')

def get_decoded_token (authorization_header):
  if authorization_header:
    auth_header = authorization_header.split(' ')

    if auth_header[0].lower() == 'bearer' and len(auth_header) > 1:
      jwt_token = auth_header[1]
    else:
      msg = 'Authorization header should be of format: Bearer <token>'
      logger.error(msg)
      raise Exception(msg)
  else:
    msg = 'Authorization header was not provided'
    logger.error(msg)
    raise Exception(msg)

  # This may throw an exception.
  # The caller should handle it
  # Use the key object for better compatibility with PyJWT 2.x and cryptography 50.x
  jwt_decoded = jwt.decode(
    jwt_token, exec_venue_public_key_object, algorithms=['RS256'])

  return jwt_decoded

def has_permission(jwt_decoded):
  scopes = jwt_decoded.get('scopes', [])
  for scope in scopes:
    # Starting R14.3, scope has both scope name and venue_group_id
    scope_name = scope.get('scope', '') if isinstance(scope, dict) else scope
    if scope_name in ACCEPTED_SCOPES:
      return True
  return False
