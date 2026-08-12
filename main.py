import logging
import sys
from starlette.concurrency import iterate_in_threadpool
from core import venue_core
import os

logger = logging.getLogger(__name__)

def print_env_variables():
    logger.info('ENVIRONMENT VARIABLES:')
    names = [
        'ING_VENUE_DIR',
        'ING_LOG_DIR',
        'CUSTOM_SCRIPT_BASE_DIR',
        'PATH'
    ]
    for name in names:
        value = os.environ.get(name)
        logger.info(f'{name}: {value}')

    for index, path in enumerate(sys.path):
        logger.info(f'sys.path {index+1}: {path}')

print_env_variables()

import traceback
import sys
import argparse
import io
import random
import string
import time

import yaml
import json
import pyaml_env
import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from fastapi.requests import Request
from fastapi.responses import JSONResponse, FileResponse, Response
# from core import core_util
from core.schema import ScriptStartBodyModel, ScriptStatusBodyModel, ScriptStatusResp, ScriptHaltBodyModel, ScriptRunInfo, \
    HealthStatus, HealthStatusEnum, ErrorResponse
from fastapi.exceptions import RequestValidationError
import utils

utils.print_key_info()

LOG_CONFIG_YAML = 'log_config.yaml'

prefix_router = APIRouter(prefix='/api/v3')


@prefix_router.get('/health', 
                    responses={
                        200: {'model': HealthStatus},
                        400: {'model': ErrorResponse}
                    },
                    summary='Check health status of VenueServer',
                    tags=['HEALTH']
                )
def health() -> HealthStatus:
    return HealthStatus(status=HealthStatusEnum.OK.value, message='')


@prefix_router.post('/custom_script/start', 
                    responses={
                        200: {'model': ScriptRunInfo},
                        400: {'model': ErrorResponse},
                        401: {'model': ErrorResponse},
                        403: {'model': ErrorResponse}
                    },
                    summary='Start execution of a custom script',
                    description='This will start the custom script and return. Use status endpoint to get its status.',
                    tags=['SCRIPT']
                )
def script_start(body: ScriptStartBodyModel, request: Request, response: Response):
    try:
        username = request.state.username
        logger.info(f'username: {username} script_start: {body}')
        body.inputs['username'] = username
        res_dict = venue_core.start_custom_script(script_path=body.scriptPath,
                                      script_hash=body.scriptHash,
                                      inputs=body.inputs,
                                      outputs=body.outputs)
        return JSONResponse(status_code=200, content=res_dict)  
    except Exception as e:
        msg = f'Failed to start a custom script: {body.scriptPath}'
        logging.exception(msg)
        response.status_code = 400
        return ErrorResponse(message=f'{msg}. {traceback.format_exc()}')


@prefix_router.get('/custom_script/{script_run_id}',
                    responses={
                        200: {'model': ScriptStatusResp},
                        400: {'model': ErrorResponse},
                        401: {'model': ErrorResponse},
                        403: {'model': ErrorResponse}
                    },
                    summary='Retrieve status information from currently executing script',
                    tags=['SCRIPT']
                )
def script_status(script_run_id: str, response: Response):
    try:
        res_dict = venue_core.get_custom_script_status(script_run_id=script_run_id)
        return JSONResponse(status_code=200, content=res_dict)

    except Exception as e:
        msg = f'Failed to get the status of custom script: {script_run_id}'
        logging.exception(msg)
        response.status_code = 400
        return ErrorResponse(message=f'{msg}. {traceback.format_exc()}')


@prefix_router.post('/custom_script/{script_run_id}/halt',
                    status_code=204,
                    responses={
                        400: {'model': ErrorResponse},
                        401: {'model': ErrorResponse},
                        403: {'model': ErrorResponse}
                    },
                    summary='Halt custom script specified',
                    tags=['SCRIPT']    
                )
def script_halt(script_run_id, response: Response):
    try:
        venue_core.halt_custom_script(script_run_id=script_run_id)
        return Response(status_code=204)
    
    except Exception as e:
        msg = f'Failed to halt custom script: {script_run_id}'
        logging.exception(msg)
        response.status_code = 400
        return ErrorResponse(message=f'{msg}. {traceback.format_exc()}')


@prefix_router.get('/custom_script/{script_run_id}/files',
                    responses={
                        200: {'content': {'application/gzip': {}}},
                        400: {'model': ErrorResponse},
                        401: {'model': ErrorResponse},
                        403: {'model': ErrorResponse}
                    },
                    summary='Download the input, output, and log files of the custom script as tar.gz',
                    tags=['SCRIPT']
                )
def script_file(script_run_id: str, response: Response):
    try:
        tar_gz_path = venue_core.get_custom_script_files(script_run_id=script_run_id)
        filename = os.path.basename(tar_gz_path)
        return FileResponse(tar_gz_path, media_type='application/gzip', filename=filename)

    except Exception as e:
        msg = f'Failed to get custom script files. script_run_id: {script_run_id}'
        logging.exception(msg)
        response.status_code = 400
        return ErrorResponse(message=f'{msg}. {traceback.format_exc()}')


# router needs to be added after end point definitions
app = FastAPI()
app.include_router(prefix_router)


@app.middleware('http')
async def check_jwt(request: Request, call_next):
    request.state.username = ''

    if request.url.path == '/docs':
        # docs end point does not require JWT token
        return await call_next(request)    
    if request.url.path == '/openapi.json':
        # docs end point does not require JWT token
        return await call_next(request)
    if request.url.path == '/openapi.yaml':
        # docs end point does not require JWT token
        return await call_next(request)
    
    if request.url.path.endswith('/health'):
        # health end point does not require JWT token
        return await call_next(request)
    else:
        authorization_header = request.headers.get('Authorization')
        try:
            jwt_decoded = utils.get_decoded_token(authorization_header)
            # cache username info for this request
            # See: https://fastapi.tiangolo.com/tutorial/sql-databases/#about-requeststate
            request.state.username = jwt_decoded.get('username', '')
        except Exception:
            return JSONResponse(status_code=401, 
                content={'message': f'Invalid API token. {traceback.format_exc()}'})

        if utils.has_permission(jwt_decoded):
            return await call_next(request)
        else:
            return JSONResponse(status_code=403, 
                content={
                    'message': f'Does not have the required permission. Need one of {utils.ACCEPTED_SCOPES}'
                })

@app.middleware('http')
async def log_request(request: Request, call_next):
    request_id = ''.join(random.choices(string.ascii_uppercase, k=6))
    logger.info(f'{request_id}: {request.method} {request.url.path}')
    start_time = time.time()
    
    response = await call_next(request)
    
    elapsed_msec = (time.time() - start_time) * 1000
    # username is available after the request has been processed
    username = request.state.username if hasattr(request.state, 'username') else ''

    # response is "StreamingResponse" class. We need to the response content as a string to log.
    # See https://stackoverflow.com/questions/71882419/fastapi-how-to-get-the-response-body-in-middleware
    content_type = response.headers.get('content-type')
    response_content = ''
    if content_type and content_type.lower() == 'application/json':
        response_body = [chunk async for chunk in response.body_iterator]
        response.body_iterator = iterate_in_threadpool(iter(response_body))
        response_content = b''.join(response_body).decode()

    log_max_chars = 1000
    if response.status_code >= 200 and response.status_code < 400:
        if len(response_content) > log_max_chars:
            logger.info(f'{request_id}: completed in {elapsed_msec:.2f} msec.' + 
                        f' status_code: {response.status_code} username: {username} response_content (total_length: {len(response_content)}): {response_content[:log_max_chars]}')
        else:
            logger.info(f'{request_id}: completed in {elapsed_msec:.2f} msec.' + 
                        f' status_code: {response.status_code} username: {username} response_content: {response_content}')
    else:
        logger.warning(f'{request_id}: completed in {elapsed_msec:.2f} msec.' + 
                    f' status_code: {response.status_code} username: {username} response_content: {response_content}')
    
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc:RequestValidationError):
    error_payload = {"detail": jsonable_encoder(exc.errors())}
    return JSONResponse(status_code=400, 
        content=error_payload)


### OPENAPI ###

tags_metadata = [
    {
        'name': 'SCRIPT',
        'description': 'Run custom scripts'
    },
    {
        'name': 'HEALTH',
        'description': 'Check service health'
    }
]

@app.get('/openapi.yaml', include_in_schema=False)
def openapi_yaml() -> Response:
    # Convert API specs in JSON to YAML.
    # See https://github.com/tiangolo/fastapi/issues/1140
    specs_json= app.openapi()
    yaml_str_io = io.StringIO()
    yaml.dump(specs_json, yaml_str_io)
    return Response(yaml_str_io.getvalue(), media_type='text/yaml')

def custom_openapi():
    try:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title='Ingenium Venue Agent',
            version='15.0',
            description='RESTful API of Ingenium Venue Agent that interfaces with test venues',
            routes=app.routes,
            tags=tags_metadata
        )

        for _, method_item in openapi_schema.get('paths').items():
            for _, param in method_item.items():
                responses = param.get('responses')
                # remove the default 422 response fro OpenAPI, which was overriden as 400 response
                if '422' in responses:
                    del responses['422']
        # cache the schema
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    except:
        logger.error(traceback.format_exc())

# override openapi method
app.openapi = custom_openapi

def parse_args():
    parser = argparse.ArgumentParser(description='Ingenium Venue Agent', 
        prog='main.py',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', '-p', type=int, default=19443,
                        help='port number of the service')
    return parser.parse_args()

if __name__ == '__main__':
    log_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), LOG_CONFIG_YAML))
    if os.path.isfile(log_config_path):
        logger.info(f'Load log configuration from: {log_config_path}')
    else:
        logger.error(f'Log configuration file does not exist. Exit. {log_config_path}')
        sys.exit(1)
    try:
        log_config = pyaml_env.parse_config(log_config_path)
    except Exception as ex:
        logger.exception(f'Failed to load log configuration file: {log_config_path}')
        sys.exit(1)

    args = parse_args()
    
    uvicorn.run('main:app', host='127.0.0.1', port=args.port, reload=False, log_config=log_config, workers=1)
