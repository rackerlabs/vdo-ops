import hashlib
import socket
import ssl
import re
from base64 import b64decode
from functools import reduce
from typing import cast, List, Any, Dict

import paramiko
from paramiko.ssh_exception import NoValidConnectionsError, AuthenticationException
from passwordgenerator import pwgenerator

from common import log

logger = log.get_logger(__name__)


class DecodeError(Exception):
    pass


class SSHException(Exception):
    pass


def get_ssl_thumbprint(host_ip: str) -> str:
    """
    Get The thumbprint of the SSL certificate, which the host is expected to have.
    example: 42:6A:9C:8C:CA:C2:A7:1B:5E:8D:56:5E:42:51:68:25:AB:C1:F2:C7

    :param host_ip:
    :return:
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        wrapped_socket = ssl.wrap_socket(sock)  # nosec
        wrapped_socket.connect((host_ip, 443))
        der_cert_bin = cast(bytes, wrapped_socket.getpeercert(True))

        thumb_sha1 = hashlib.sha1(der_cert_bin).hexdigest()  # nosec
    finally:
        wrapped_socket.close()

    elements = list(
        map(lambda x: f"{thumb_sha1[x: (x + 2)]}", range(0, len(thumb_sha1), 2))
    )

    thumbprint = reduce(lambda x, y: f"{x}:{y}", elements).upper()

    logger.debug(f"Host {host_ip} has thumbprint: {thumbprint}")

    return thumbprint


def unique_list(objects: List[Any], key_name: str) -> List[Any]:
    """
    Get a unique list

    :param objects:
    :param key_name:
    :return:
    """

    data: Dict[str, Any] = {}
    for object in objects:
        key = getattr(object, key_name)

        if key not in data:
            data[key] = object

    return list(data.values())


def generate_password() -> str:
    """
    Generates a password that is within 20 characters long and replaces ; with @
    """
    password = pwgenerator.pw(
        min_word_length=4, max_word_length=4, number_of_elements=3
    )
    return str(password.replace(";", "@"))


def decode(encoded_str: str) -> Any:
    """Decode an encrypted HTTP basic authentication string. Returns a tuple of
    the form (username, password), and raises a DecodeError exception if
    nothing could be decoded.
    From: https://github.com/rdegges/python-basicauth/blob/master/basicauth.py
    """
    split = encoded_str.strip().split(" ")

    # If split is only one element, try to decode the username and password
    # directly.
    if len(split) == 1:
        try:
            username, password = b64decode(split[0]).decode().split(":", 1)
        except Exception:
            raise DecodeError

    # If there are only two elements, check the first and ensure it says
    # 'basic' so that we know we're about to decode the right thing. If not,
    # bail out.
    elif len(split) == 2:
        if split[0].strip().lower() == "basic":
            try:
                username, password = b64decode(split[1]).decode().split(":", 1)
            except Exception:
                raise DecodeError
        else:
            raise DecodeError

    # If there are more than 2 elements, something crazy must be happening.
    # Bail.
    else:
        raise DecodeError

    return str(username), str(password)


def is_sshable(host: str, username: str, password: str, port: int = 22) -> bool:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host, port=port, username=username, password=password, timeout=5
        )
    except (socket.gaierror, socket.timeout, NoValidConnectionsError):
        logger.exception(f"Not able to connect {host}")

        return False
    except AuthenticationException:
        logger.exception("Wrong username or password")

        return False
    except Exception:
        logger.exception(
            "Caught unexpected exception. Assume it is caused by failed ssh "
            "connection. This needs investigation"
        )

        return False
    finally:
        client.close()

    return True


def execute_ssh_cmd(username: str, password: str, ip: str, cmd: str) -> Any:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)  # nosec
    client.connect(
        hostname=ip, username=username, password=password,
    )
    try:
        error_str = ""
        stdin, stdout, stderr = client.exec_command(cmd)  # nosec
        error_lines = stderr.readlines()
        if error_lines:
            logger.exception(f"SSH command failed to execute: {cmd}")
            for line in error_lines:
                error_str += line.strip() + "\n"
            raise SSHException(error_str)
        return stdout
    finally:
        client.close()


def compile_ant_path(path: str) -> str:
    """
    Given a path, converts it to an ANT path regex
    :param path:
    :return:
    """
    star = r"[^\/]+"
    double_star = r".*"
    slash = r"\/"
    question_mark = r"\w"
    dot = r"\."
    # Apply transformation
    output = path.replace(r"/", slash).replace(r".", dot)
    output = re.sub(r"(?<!\*)\*(?!\*)", star, output)
    output = output.replace(r"**", double_star)
    output = output.replace(r"?", question_mark)
    return output
