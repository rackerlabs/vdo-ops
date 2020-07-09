from typing import Any, Optional

import arrow
from requests import Session


class IdentityAccount:
    def __init__(
        self,
        identity_endpoint: str,
        username: str,
        password: str,
        domain: str = "Rackspace",
    ) -> None:
        self.__identity_endpoint = identity_endpoint
        self.__username = username
        self.__password = password
        self.__domain = domain
        self.__token: Optional[str] = None
        self.__expire_time = None

    def __refresh_token(self) -> None:
        data = {
            "auth": {
                "passwordCredentials": {
                    "username": self.__username,
                    "password": self.__password,
                }
            }
        }

        if self.__domain:
            data["auth"]["RAX-AUTH:domain"] = {"name": self.__domain}

        with BaseSession() as s:
            r = s.post(f"{self.__identity_endpoint}/v2.0/tokens", json=data)

            r.raise_for_status()

            response = r.json()

        self.__expire_time = response["access"]["token"]["expires"]
        self.__token = response["access"]["token"]["id"]

    @property
    def token(self) -> str:
        if self.__expire_time is not None:
            current_time = arrow.utcnow()
            expire_time = arrow.get(self.__expire_time)

            if current_time.shift(minutes=+10) < expire_time:
                return self.__token

        # it should be ok right now even token is updated twice at the same time
        # since it won't hurt
        self.__refresh_token()

        return self.__token


class SessionConfig:
    def __init__(
        self,
        read_timeout: int = 5,
        connect_timeout: int = 5,
        accept: str = "application/json",
        content_type: str = "application/json",
    ):
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self.accept = accept
        self.content_type = content_type


DEFAULT_SESSION_CONFIG = SessionConfig()


class BaseSession(Session):
    def __init__(self, session_config: SessionConfig = DEFAULT_SESSION_CONFIG):
        super().__init__()

        self.__session_config = session_config
        self.headers["Accept"] = session_config.accept
        self.headers["Content-Type"] = session_config.content_type

    def request(self, method: str, url: str, **kwargs: Any):  # type: ignore
        if "timeout" not in kwargs:
            kwargs["timeout"] = (
                self.__session_config.connect_timeout,
                self.__session_config.read_timeout,
            )

        return super().request(method, url, **kwargs)


class IdentitySession(BaseSession):
    def __init__(
        self,
        identity_account: IdentityAccount,
        session_config: SessionConfig = DEFAULT_SESSION_CONFIG,
    ):
        super().__init__(session_config)

        self.__identity_account = identity_account

    def prepare_request(self, request):  # type: ignore
        p = super().prepare_request(request)  # type: ignore

        p.headers["x-auth-token"] = self.__identity_account.token

        return p
