import os
from pathlib import Path
from typing import Any, Dict, Union, Tuple
from uuid import uuid4

import awsgi
import marshmallow
import structlog
from flask import Flask, json, globals
from flask_dotenv import DotEnv
from flask_rebar import errors

from common import log, constants
from controllers import job, host  # noqa: F401
from schemas.error import ErrorResponseSchema
from server.rebar import rebar

logger = log.get_logger(__file__)


def create_app() -> Flask:
    app = Flask(__name__)
    dot_env = DotEnv()
    env_path = Path(os.path.abspath(__file__)).parent.parent
    stage = constants.STAGE
    if stage != "prod":
        stage = "dev"
    logger.debug("Initializing for stage", stage=stage)
    env_file = os.path.join(env_path, f".env.{stage}")
    dot_env.init_app(app, env_file=env_file, verbose_mode=True)

    rebar.init_app(app)
    logger.debug("Routes configured", routes=app.url_map)

    @app.before_request
    def before_request() -> None:
        name = (
            globals.request.environ.get("awsgi.event", {})
            .get("requestContext", {})
            .get("authorizer", {})
            .get("name")
        )
        endpoint = globals.request.full_path

        logger.info("Received request", endpoint=endpoint, name=name)

    @app.teardown_request
    def cleanup(exc: Union[Exception, None]) -> None:
        logger.debug("Cleaning logging context")

        structlog.threadlocal.clear_threadlocal()

    # put after rebar initialization to override rebar's default handler
    @app.errorhandler(errors.HttpJsonError)
    def handle_http_error(error: errors.HttpJsonError) -> None:
        """
        Override default rebar exception handler for HttpJsonError.
        :param error:
        :return:
        """
        raise

    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception) -> Any:
        if app.debug:
            raise error
        (data, status_code) = __handle_generic_error(error)

        resp = json.jsonify(data)
        resp.status_code = status_code

        return resp

    return app


def __handle_generic_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    error_id = str(uuid4())

    logger.exception(error, error_id=error_id)

    if isinstance(error, errors.HttpJsonError):
        status_code = error.http_status_code
        additional_data = error.additional_data

        if isinstance(error.__context__, marshmallow.ValidationError):
            error_message = (
                f"Request is invalid on fields {error.__context__.field_names}"
            )
        else:
            error_message = error.error_message
    else:
        error_message = "Internal Server Error"
        status_code = 500
        additional_data = None

    data = (
        ErrorResponseSchema()
        .load(
            {
                "error": {
                    "id": error_id,
                    "message": error_message,
                    "data": additional_data,
                }
            }
        )
        .data
    )
    return data, status_code


def run_app() -> None:
    create_app().run()


def handler(event: Dict[str, Any], context: object) -> Any:
    domain_id = (
        event.get("requestContext", {}).get("authorizer", {}).get("domainId", None)
    )
    if domain_id is not None:
        event.get("headers")["x-tenant-id"] = domain_id

    app = create_app()
    base64_types = ["image/png"]
    return awsgi.response(app, event, context, base64_content_types=base64_types)
