from __future__ import annotations

from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
import certifi

from .config import settings


def get_plaid_client() -> plaid_api.PlaidApi:
    """Create a Plaid API client using server-side credentials only."""
    env = (settings.plaid_env or "sandbox").lower()
    if env == "sandbox":
        host = "https://sandbox.plaid.com"
    elif env == "production":
        host = "https://production.plaid.com"
    else:
        raise ValueError("PLAID_ENV must be 'sandbox' or 'production'")

    if not settings.plaid_client_id or not settings.plaid_secret:
        raise ValueError("PLAID_CLIENT_ID and PLAID_SECRET are required when DEMO_MODE=false")

    configuration = Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
        # Use a maintained CA bundle instead of relying on the host Python
        # installation's certificate store.
        ssl_ca_cert=certifi.where(),
    )
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def close_plaid_client(client: plaid_api.PlaidApi) -> None:
    # plaid-python exposes the underlying ApiClient on the generated client.
    api_client = getattr(client, "api_client", None)
    close = getattr(api_client, "close", None)
    if callable(close):
        close()
