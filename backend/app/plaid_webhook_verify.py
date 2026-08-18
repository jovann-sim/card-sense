from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import jwt
from jwt import algorithms
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .plaid_client import get_plaid_client

# Plaid signs every webhook body with a JWT in the Plaid-Verification header,
# using a key it publishes through its own API rather than a shared secret —
# there is nothing to configure here, only a call to verify against. This is
# their documented scheme (https://plaid.com/docs/api/webhooks/webhook-verification),
# not a partial or simplified version of it: signature, key freshness and a
# hash of the exact bytes that were sent, all three checked.
#
# Without this, the webhook endpoint trusted its own request body: anyone who
# found the URL could POST a fake SYNC_UPDATES_AVAILABLE and make the backend
# pull from Plaid on demand. Nothing destructive follows from that today, but
# it is the one endpoint in this product whose entire job is to be called by
# someone other than the user, and it was not checking who.

# Plaid rotates signing keys; caching them for the process lifetime avoids a
# key lookup on every webhook while still tolerating rotation, because a kid
# this cache has not seen triggers a fresh fetch below.
_KEY_CACHE: dict[str, str] = {}

# Plaid recommends rejecting a JWT whose issued-at claim is older than this,
# which bounds how long a captured request stays replayable.
MAX_AGE_SECONDS = 5 * 60


class WebhookVerificationError(Exception):
    """A webhook that did not pass verification. Never processed, always logged."""


@dataclass
class VerifiedWebhook:
    body: dict


def _signing_key_pem(key_id: str) -> str:
    if key_id in _KEY_CACHE:
        return _KEY_CACHE[key_id]

    from plaid.model.webhook_verification_key_get_request import WebhookVerificationKeyGetRequest

    client = get_plaid_client()
    response = client.webhook_verification_key_get(
        WebhookVerificationKeyGetRequest(key_id=key_id)
    ).to_dict()
    jwk = response.get("key")
    if not jwk or jwk.get("expired_at"):
        raise WebhookVerificationError(f"No usable signing key for kid {key_id!r}")

    import json as _json
    public_key = algorithms.ECAlgorithm.from_jwk(_json.dumps(jwk))
    pem = public_key.public_bytes(
        encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
    ).decode()
    _KEY_CACHE[key_id] = pem
    return pem


def verify(raw_body: bytes, verification_header: str | None) -> VerifiedWebhook:
    """Check a webhook's signature, freshness and body hash, or raise.

    `raw_body` must be the exact bytes Plaid sent — re-serialising a parsed
    dict and hashing that would not match, since JSON key order and spacing
    are not canonical. This is why the endpoint reads the request body itself
    rather than accepting a pre-parsed model.
    """
    if not verification_header:
        raise WebhookVerificationError("Missing Plaid-Verification header")

    try:
        unverified_header = jwt.get_unverified_header(verification_header)
    except jwt.InvalidTokenError as exc:
        raise WebhookVerificationError(f"Malformed verification token: {exc}") from exc

    key_id = unverified_header.get("kid")
    if not key_id:
        raise WebhookVerificationError("Verification token has no key id")

    try:
        signing_key = _signing_key_pem(key_id)
        claims = jwt.decode(verification_header, signing_key, algorithms=["ES256"])
    except jwt.InvalidTokenError as exc:
        raise WebhookVerificationError(f"Signature check failed: {exc}") from exc

    issued_at = claims.get("iat")
    if not isinstance(issued_at, (int, float)) or time.time() - issued_at > MAX_AGE_SECONDS:
        raise WebhookVerificationError("Verification token is stale or has no issued-at claim")

    expected_hash = claims.get("request_body_sha256")
    actual_hash = hashlib.sha256(raw_body).hexdigest()
    if not expected_hash or expected_hash != actual_hash:
        raise WebhookVerificationError("Request body does not match its signed hash")

    import json
    return VerifiedWebhook(body=json.loads(raw_body or b"{}"))
