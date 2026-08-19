from app import plaid_client


def test_plaid_credentials_are_stripped_before_becoming_headers(monkeypatch):
    """Secret Manager values created with echo can contain a final newline."""
    captured = {}

    class CapturingApiClient:
        def __init__(self, configuration):
            captured["configuration"] = configuration

    class CapturingPlaidApi:
        def __init__(self, api_client):
            self.api_client = api_client

    monkeypatch.setattr(plaid_client, "ApiClient", CapturingApiClient)
    monkeypatch.setattr(plaid_client.plaid_api, "PlaidApi", CapturingPlaidApi)
    monkeypatch.setattr(plaid_client.settings, "plaid_env", "sandbox")
    monkeypatch.setattr(plaid_client.settings, "plaid_client_id", " client-id\n")
    monkeypatch.setattr(plaid_client.settings, "plaid_secret", "secret-value\n")

    plaid_client.get_plaid_client()

    configuration = captured["configuration"]
    assert configuration.api_key["clientId"] == "client-id"
    assert configuration.api_key["secret"] == "secret-value"
