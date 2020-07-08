from fleece import requests
from fleece.xray import monkey_patch_requests_for_xray

monkey_patch_requests_for_xray()

# Configure retries into requests in case networking
# or a service is having a bad day.
requests.set_default_timeout(30)
requests.set_default_retries(
    backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504], total=5
)
