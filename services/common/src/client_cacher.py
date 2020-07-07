from functools import partial

import boto3

from common import config, identity, janus


class Cacheable(type):
    """
    Implements magic property caching. If added to a class, all method names
    that start with "cache_" will have private properties created and get, set,
    and delete functions set for it. The get will fetch and store an object
    into the internal cache upon first access.

    As an example, let's say you want to cache a client object called foosystem.
    You can create a class with a method definition `cache_foosystem(self)` that
    returns the foosystem client object. The Cacheable type will create
    self._foosystem to store the client, and create the property
    `self.foosystem` with getter, setter, and deleter. You can choose to
    override the property functions by creating your own methods such as
    `get_foosystem`, `set_foosystem`, or `del_foosystem` and they will be
    injected instead of the standard generic ones.
    """

    def __init__(cls, name, bases, nmspc):
        super(Cacheable, cls).__init__(name, bases, nmspc)
        for k in nmspc.copy().keys():
            if k.startswith("cache_"):
                root_var = k[6:]
                getter = f"get_{root_var}"
                setter = f"set_{root_var}"
                finder_funcs = {
                    "get": partial(Cacheable.get_generic, root_var),
                    "set": partial(Cacheable.set_generic, root_var),
                    "del": partial(Cacheable.del_generic, root_var),
                }
                for prefix in finder_funcs.keys():
                    finder = f"{prefix}_{root_var}"
                    if finder in dir(cls):
                        finder_funcs[prefix] = getattr(cls, finder)
                getter = finder_funcs["get"]
                setter = finder_funcs["set"]
                deler = finder_funcs["del"]
                setattr(cls, root_var, property(getter, setter, deler))

    def get_generic(field_name, cls):
        private_var = f"_{field_name}"
        try:
            return getattr(cls, private_var)
        except AttributeError:
            client_obj = getattr(cls, f"cache{private_var}")()
            setattr(cls, private_var, client_obj)
            return client_obj

    def set_generic(field_name, cls, value):
        setattr(cls, f"_{field_name}", value)

    def del_generic(field_name, cls):
        delattr(cls, f"_{field_name}")


class ClientCacher(object, metaclass=Cacheable):
    """
    Object to hold all our client connections, primarily for caching between
    lambda runs. Lambdas can just call the clients via the class properties
    the class properties and let the fetching happen behind the scenes:

    CLIENTS = client_cacher.ClientCacher()
    CLIENTS.janus_client.delete_all_ddis(force=True)
    """

    def __init__(self, aws_account=None, domain=None, region=None):
        """
        AWS info is required for aws clients, but those dont really exist
        outside the sfn context. You can change `aws_auth_account` and `domain`
        in your handler() and the object will mark the existing creds as dirty
        and fetch new ones the next time you request them.

        Caveat: `region` can change without marking credentials as dirty.

        Keyword Arguments:
            aws_account (string): AWS account name
            domain (string): While the janus api will process many
                values, in the current context of this client we are expecting
                it to be the DDI (rackspace account number) though that could
                thoeretically be other valid values like "Rackspace".
            region (string): The aws region you wish to modify.

        Other notes:
            self.__aws_creds_dirty (bool): A toggle to know whether or not we
                need to refresh the creds (i.e., the username/domain changed).
        """
        self.__aws_creds_dirty = False
        self.region = region
        if None in [aws_account, domain]:
            self._aws_account = None
            self._domain = None
        else:
            self._aws_account = str(aws_account)
            self._domain = str(domain)

    def __get_boto_client(self, client_type):
        if "_boto_session" not in vars(self):
            self._boto_session = boto3.session.Session(
                region_name=self.region, **self.aws_creds
            )
        return self._boto_session.client(client_type)

    def __change_aws_field(self, field_name, field_val):
        """
        Sets the internal attribute and dirty flag if needed. Force type string
        because aws is type sensitive for reasons that don't make sense.
        """
        if field_name not in vars(self) or field_val != getattr(self, field_name):
            setattr(self, field_name, str(field_val))
            self.__aws_creds_dirty = True

    @property
    def aws_account(self):
        return self._aws_account

    @aws_account.setter
    def aws_account(self, newval):
        self.__change_aws_field("_aws_account", newval)

    @property
    def domain(self):
        return self._domain

    @domain.setter
    def domain(self, newval):
        self.__change_aws_field("_domain", newval)

    def get_aws_creds(self):
        if "_aws_creds" not in vars(self) or self.__aws_creds_dirty is True:
            self._aws_creds = self.cache_aws_creds()
            self.__aws_creds_dirty = False
        return self._aws_creds

    def cache_secrets(self):
        return config.get_secrets_from_ssm()

    def cache_aws_creds(self):
        """
        In the event of iam based access, we just use None here becaues
        that's what boto takes directly, thus making passwords unnecessary.
        """
        creds = {
            "aws_access_key_id": None,
            "aws_secret_access_key": None,
            "aws_session_token": None,
        }
        if None not in [self.aws_account, self.domain]:
            resp = self.janus_client.get_credentials(self.aws_account, self.domain)
            creds["aws_access_key_id"] = resp["accessKeyId"]
            creds["aws_secret_access_key"] = resp["secretAccessKey"]
            creds["aws_session_token"] = resp["sessionToken"]
        return creds

    def cache_cloudwatch_client(self):
        return self.__get_boto_client("cloudwatch")

    def cache_iam_client(self):
        return self.__get_boto_client("iam")

    def cache_ssm_client(self):
        return self.__get_boto_client("ssm")

    def cache_s3_client(self):
        return self.__get_boto_client("s3")

    def cache_sts_client(self):
        return self.__get_boto_client("sts")

    def cache_sfn_client(self):
        return self.__get_boto_client("stepfunctions")

    def cache_identity_client(self):
        return identity.RackspaceIdentity(
            self.secrets.get("service_account_username"),
            self.secrets.get("service_account_password"),
            domain="Rackspace",
        )

    def cache_janus_client(self):
        return janus.JanusClient(token=self.identity_client.token)
