"""
hatun_mcp.payment_context - origin-side check of Cloudflare's x402 PAYMENT-CONTEXT.

Cloudflare Monetization Gateway charges a matching request at the edge and then
forwards it to the origin with a ``PAYMENT-CONTEXT`` header: an Ed25519-signed
JWT. Cloudflare's payment-validation guidance requires the origin to verify that
token against the pinned JWKS (https://payments.cloudflare.com/certs) with a JWT
library, to treat a missing header as unpaid, to cache keys according to the
endpoint's ``Cache-Control`` header, and, for the variable ``upto`` scheme only,
to report the actual amount in ``PAYMENT-SETTLEMENT`` on a successful response.

What a ``VerifiedPayment`` proves, and what it does not
-------------------------------------------------------
It proves that a key published at the pinned JWKS URL signed an authorisation of
exactly ``amount`` atomic units under ``scheme`` for exactly this audience, and
that the token is inside its validity window (with a bounded clock leeway). It
is not evidence that the payment settled, who paid, or that the request is
unique. The documented claims carry no payer, nonce or ``jti``. Ed25519
signatures are deterministic, so two authorisations with identical claims in the
same second are byte-identical tokens. A replay cache would reject the second
buyer, so this module does not keep one.

Fail-closed rules
-----------------
* Malformed tokens, any ``alg`` other than ``EdDSA``, and token-supplied key
  material (``jku``, ``jwk``, ``x5u``, ``x5c``) are rejected before any key
  retrieval. ``crit`` and ``b64`` are not supported.
* Keys come only from the pinned URL. Redirects are not followed, environment
  proxies and credentials are not inherited, and the body and the time are both
  bounded. Every key must be a public Ed25519 ``OKP`` key.
* Expired keys are never used again, even if the refetch fails. If no fresh key
  set is available, verification raises ``PaymentKeysUnavailable`` and the
  caller must refuse the request.
* An unknown ``kid`` forces at most one refetch per 60 seconds. This picks up a
  key rotation without letting callers drive unbounded fetches.
* ``aud`` must be a string equal to the expected audience. ``scheme`` and
  ``amount`` must equal the configured terms, so a payment made under a cheaper
  rule is refused. ``iat``, ``nbf`` and ``exp`` must be integers.

Provenance
----------
This is a port, not a new design. The claim checks and reason codes follow
szl-holdings/szl-trust ``scripts/x402_payment_context.py``. The key handling
(pinned JWKS, Cache-Control freshness with Age and Date, strict Ed25519 key
validation, no stale fallback, coalesced retrieval) follows
``ops/evidence-snapshot-worker/src/payment-keys.mjs``. Both are at szl-trust
commit d23e471, (c) SZL Holdings, CC BY 4.0, and are adapted here under
Apache-2.0.

Changes from those sources: JWKS retrieval in Python with httpx; a required
expected amount (the szl-trust script parsed the amount but did not compare it);
a bounded default leeway of 5 s (the Worker's tolerance) instead of an
unbounded-to-120 s parameter; a typed outage error; at most one forced refresh
for an unknown ``kid``; and the ``upto`` settlement helper.

This module imports nothing from hatun_mcp, so it can move unchanged into a
shared package.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import email.utils
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timezone
from typing import Awaitable, Callable, Mapping, Optional

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jwt.exceptions import (
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
    PyJWTError,
)

JWKS_URL = "https://payments.cloudflare.com/certs"
ALGORITHM = "EdDSA"
SCHEMES = frozenset({"exact", "upto"})
MIN_ATOMIC = 1_000  # $0.001: the documented minimum price and settlement.
MAX_ATOMIC = 100_000_000  # $100: the documented maximum price.
DEFAULT_LEEWAY_SECONDS = 5  # The evidence-snapshot Worker's clock tolerance.
MAX_LEEWAY_SECONDS = 30
MAX_TOKEN_CHARS = 8 * 1024
MAX_JWKS_BYTES = 64 * 1024
MAX_JWKS_KEYS = 32
JWKS_FETCH_TIMEOUT_SECONDS = 5.0
MAX_KEY_CACHE_SECONDS = 24 * 60 * 60
UNKNOWN_KID_REFRESH_SECONDS = 60.0
TOKEN_KEY_HEADERS = frozenset({"jku", "jwk", "x5u", "x5c"})
UNSUPPORTED_HEADERS = frozenset({"crit", "b64"})

_ATOMIC = re.compile(r"(?:0|[1-9][0-9]*)")
_SEGMENT = re.compile(r"[A-Za-z0-9_-]+")
_ED25519_X = re.compile(r"[A-Za-z0-9_-]{43}")
_JWKS_CONTENT_TYPE = re.compile(r"application/(?:json|jwk-set\+json)(?:\s*;|\Z)", re.IGNORECASE)
_DIGITS = re.compile(r"[0-9]{1,12}")
_QUOTED_DIGITS = re.compile(r'"([0-9]{1,12})"')
_MAX_ATOMIC_DIGITS = len(str(MAX_ATOMIC))
_LOG = logging.getLogger(__name__)


class PaymentContextInvalid(Exception):
    """The presented context is not a valid authorisation for these terms."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class PaymentKeysUnavailable(Exception):
    """No fresh pinned key set is available, so nothing can be verified."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parse_atomic_amount(value: object) -> int:
    """Return canonical decimal atomic units within the documented price range.

    Raises ``ValueError`` with reason ``MALFORMED_AMOUNT`` or
    ``AMOUNT_OUT_OF_BOUNDS``. The digit count is bounded before ``int()``, so an
    oversized string cannot reach the interpreter's integer-conversion limit.
    """
    if type(value) is not str or _ATOMIC.fullmatch(value) is None:
        raise ValueError("MALFORMED_AMOUNT")
    if len(value) > _MAX_ATOMIC_DIGITS:
        raise ValueError("AMOUNT_OUT_OF_BOUNDS")
    amount = int(value)
    if not MIN_ATOMIC <= amount <= MAX_ATOMIC:
        raise ValueError("AMOUNT_OUT_OF_BOUNDS")
    return amount


def settlement_header_value(
    *, scheme: str, status_code: int, actual: int, authorized: int
) -> Optional[str]:
    """Return the ``PAYMENT-SETTLEMENT`` value, or ``None`` when it must be absent.

    Fixed (``exact``) pricing never sets the header, because the gateway settles
    the signed amount. A response with status 400 or higher never sets it. An
    ``upto`` response reports ``0 <= actual <= authorized`` atomic units. Zero
    means nothing is settled.
    """
    if type(status_code) is not int:
        raise ValueError("BAD_STATUS")
    if scheme not in SCHEMES:
        raise ValueError("UNKNOWN_SCHEME")
    if scheme == "exact" or status_code >= 400:
        return None
    if type(actual) is not int or type(authorized) is not int:
        raise ValueError("INTEGER_ATOMIC_AMOUNTS_REQUIRED")
    if not 0 <= actual <= authorized:
        raise ValueError("AMOUNT_OUT_OF_BOUNDS")
    return json.dumps({"amount": str(actual)}, separators=(",", ":"))


@dataclass(frozen=True)
class PaymentTerms:
    """What one origin URL sells: the exact audience, scheme and atomic amount."""

    audience: str
    scheme: str
    amount: int

    def __post_init__(self) -> None:
        if self.scheme not in SCHEMES:
            raise ValueError("payment scheme must be exact or upto")
        if type(self.amount) is not int or not MIN_ATOMIC <= self.amount <= MAX_ATOMIC:
            raise ValueError("payment amount must be integer atomic units in [1000, 100000000]")
        if (
            not isinstance(self.audience, str)
            or not self.audience.startswith(("https://", "http://"))
            or any(c.isspace() for c in self.audience)
        ):
            raise ValueError("payment audience must be an absolute URL")


@dataclass(frozen=True)
class VerifiedPayment:
    """A verified authorisation. Never carries the raw token."""

    audience: str
    scheme: str
    amount: int
    iat: int
    nbf: int
    exp: int
    kid: Optional[str]
    context_sha256: str

    def receipt_fields(self) -> dict:
        """Public, non-secret facts suitable for a signed receipt."""
        return {
            "protocol": "x402",
            "header": "PAYMENT-CONTEXT",
            "verified": True,
            "jwks": JWKS_URL,
            "kid": self.kid,
            "scheme": self.scheme,
            "authorized_amount_atomic": str(self.amount),
            "audience": self.audience,
            "iat": self.iat,
            "nbf": self.nbf,
            "exp": self.exp,
            "context_sha256": self.context_sha256,
            "settlement_evidence": False,
        }


@dataclass
class PaymentAdmission:
    """One verified payment bound to one request, plus the governed outcomes it saw."""

    payment: VerifiedPayment
    outcomes: list = field(default_factory=list)

    def receipt_fields(self) -> dict:
        return self.payment.receipt_fields()

    def record(self, *, tool: str, status: str) -> None:
        self.outcomes.append((tool, status))

    def succeeded(self, tool: str) -> bool:
        """True only when exactly one governed call ran and it was ``tool`` succeeding."""
        return self.outcomes == [(tool, "success")]


@dataclass(frozen=True)
class JwksResponse:
    """The parts of a JWKS HTTP response that the checks use."""

    status: int
    headers: httpx.Headers
    body: bytes
    url: str


FetchJwks = Callable[[], Awaitable[JwksResponse]]


async def fetch_pinned_jwks(
    *, transport: Optional[httpx.AsyncBaseTransport] = None
) -> JwksResponse:
    """GET the pinned JWKS with bounded time and body.

    Redirects are not followed, and environment proxies, credentials and CA
    overrides are not inherited. ``transport`` exists only for hermetic tests.
    At most one byte past the size limit is kept, so ``parse_jwks`` can reject
    an oversized body without this function buffering all of it.
    """
    async with asyncio.timeout(JWKS_FETCH_TIMEOUT_SECONDS):
        async with httpx.AsyncClient(
            timeout=JWKS_FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            headers={"accept": "application/json"},
            transport=transport,
        ) as client:
            async with client.stream("GET", JWKS_URL) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk[: MAX_JWKS_BYTES + 1 - len(body)])
                    if len(body) > MAX_JWKS_BYTES:
                        break
                return JwksResponse(
                    status=response.status_code,
                    headers=response.headers,
                    body=bytes(body),
                    url=str(response.url),
                )


def freshness_seconds(
    headers: Mapping[str, str], started_at: float, received_at: float
) -> float:
    """Seconds the response may be reused, from Cache-Control, Age and Date.

    Port of the Worker's ``freshness``. Duplicate directives, ``no-cache``,
    ``no-store`` and malformed ``max-age`` or ``Age`` values all mean "do not
    reuse". The corrected age includes the retrieval delay. Reuse is also capped
    at 24 hours.
    """
    directives: dict[str, str] = {}
    for part in (headers.get("cache-control") or "").split(","):
        name, _, value = part.strip().lower().partition("=")
        if not name:
            continue
        if name in directives:
            return 0.0
        directives[name] = value.strip()
    if "no-cache" in directives or "no-store" in directives:
        return 0.0
    max_age = directives.get("max-age", "")
    quoted = _QUOTED_DIGITS.fullmatch(max_age)
    if quoted is not None:
        max_age = quoted.group(1)
    age = headers.get("age")
    if age is None:
        age = "0"
    if _DIGITS.fullmatch(max_age) is None or _DIGITS.fullmatch(age) is None:
        return 0.0
    lifetime = min(int(max_age), MAX_KEY_CACHE_SECONDS)
    apparent_age = 0.0
    date = headers.get("date")
    if date:
        try:
            sent = email.utils.parsedate_to_datetime(date)
        except (TypeError, ValueError, IndexError, OverflowError):
            sent = None
        if sent is not None:
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            apparent_age = max(0.0, received_at - sent.timestamp())
    corrected_age = max(apparent_age, int(age) + max(0.0, received_at - started_at))
    return max(0.0, lifetime - corrected_age)


def _ed25519_key(jwk: object) -> Ed25519PublicKey:
    if (
        not isinstance(jwk, dict)
        or jwk.get("kty") != "OKP"
        or jwk.get("crv") != "Ed25519"
        or type(jwk.get("x")) is not str
        or _ED25519_X.fullmatch(jwk["x"]) is None
        or "d" in jwk
        or ("alg" in jwk and jwk["alg"] != ALGORITHM)
        or ("use" in jwk and jwk["use"] != "sig")
        or ("kid" in jwk and type(jwk["kid"]) is not str)
        or ("key_ops" in jwk and jwk["key_ops"] != ["verify"])
    ):
        raise PaymentKeysUnavailable("PAYMENT_KEYS_ED25519_REQUIRED")
    try:
        return Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(jwk["x"] + "="))
    except (ValueError, binascii.Error):
        raise PaymentKeysUnavailable("PAYMENT_KEYS_ED25519_REQUIRED") from None


@dataclass(frozen=True)
class _KeySet:
    by_kid: Mapping[str, Optional[Ed25519PublicKey]]
    keys: tuple
    fetched_at: float
    expires_at: float

    def lookup(self, kid: Optional[str]) -> Optional[Ed25519PublicKey]:
        if kid is None:
            # A token without kid is accepted only against a single-key set.
            return self.keys[0] if len(self.keys) == 1 else None
        return self.by_kid.get(kid)


def parse_jwks(response: JwksResponse) -> tuple[dict, tuple]:
    """Validate a pinned-JWKS response. Returns ``(by_kid, keys)``.

    A ``kid`` that appears twice maps to ``None``, so it can never select a key.
    """
    if response.status != 200 or response.url != JWKS_URL:
        raise PaymentKeysUnavailable("PAYMENT_KEYS_RESPONSE_INVALID")
    if _JWKS_CONTENT_TYPE.match(response.headers.get("content-type", "")) is None:
        raise PaymentKeysUnavailable("PAYMENT_KEYS_CONTENT_TYPE_INVALID")
    if len(response.body) > MAX_JWKS_BYTES:
        raise PaymentKeysUnavailable("PAYMENT_KEYS_BODY_TOO_LARGE")
    try:
        document = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise PaymentKeysUnavailable("PAYMENT_KEYS_SET_INVALID") from None
    entries = document.get("keys") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_JWKS_KEYS:
        raise PaymentKeysUnavailable("PAYMENT_KEYS_SET_INVALID")
    by_kid: dict[str, Optional[Ed25519PublicKey]] = {}
    keys = []
    for jwk in entries:
        key = _ed25519_key(jwk)
        keys.append(key)
        kid = jwk.get("kid")
        if kid is not None:
            by_kid[kid] = None if kid in by_kid else key
    return by_kid, tuple(keys)


class PaymentKeyResolver:
    """Pinned-JWKS key source: Cache-Control freshness and no stale fallback."""

    def __init__(
        self,
        *,
        fetch: Optional[FetchJwks] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch = fetch or fetch_pinned_jwks
        self._clock = clock
        self._cached: Optional[_KeySet] = None
        self._inflight: Optional[tuple] = None

    async def _retrieve(self) -> _KeySet:
        started = self._clock()
        try:
            response = await self._fetch()
        except PaymentKeysUnavailable:
            raise
        except Exception as exc:
            # Transport errors and timeouts. Only the class name is logged; the
            # message stays out of logs and responses.
            _LOG.warning(json.dumps({"event": "payment_keys_fetch_failed",
                                     "error": type(exc).__name__}))
            raise PaymentKeysUnavailable("PAYMENT_KEYS_FETCH_FAILED") from None
        received = self._clock()
        by_kid, keys = parse_jwks(response)
        lifetime = freshness_seconds(response.headers, started, received)
        return _KeySet(by_kid, keys, fetched_at=received, expires_at=received + lifetime)

    async def _retrieve_and_store(self) -> _KeySet:
        try:
            keyset = await self._retrieve()
        finally:
            current = self._inflight
            if current is not None and current[1] is asyncio.current_task():
                self._inflight = None
        # A no-store or already-expired answer serves this flight only.
        self._cached = keyset if self._clock() < keyset.expires_at else None
        return keyset

    async def _refresh(self) -> _KeySet:
        """Start one retrieval per event loop, or join the one in flight."""
        loop = asyncio.get_running_loop()
        current = self._inflight
        if current is None or current[0] is not loop or current[1].done():
            task = loop.create_task(self._retrieve_and_store())
            task.add_done_callback(_consume_outcome)
            current = (loop, task)
            self._inflight = current
        # Shielded: one caller's cancellation does not cancel the shared fetch.
        return await asyncio.shield(current[1])

    async def _current(self) -> _KeySet:
        cached = self._cached
        if cached is not None and self._clock() < cached.expires_at:
            return cached
        self._cached = None  # Expired keys are never reused, even if the refetch fails.
        return await self._refresh()

    async def key_for(self, kid: Optional[str]) -> Ed25519PublicKey:
        keyset = await self._current()
        key = keyset.lookup(kid)
        if key is None and self._clock() - keyset.fetched_at >= UNKNOWN_KID_REFRESH_SECONDS:
            keyset = await self._refresh()
            key = keyset.lookup(kid)
        if key is None:
            raise PaymentContextInvalid("UNKNOWN_KEY")
        return key


def _consume_outcome(task: asyncio.Task) -> None:
    # Waiters that were cancelled never await the shared task; read its
    # exception here so asyncio does not log it as never retrieved.
    if not task.cancelled():
        task.exception()


def protected_header(token: object) -> dict:
    """Check the JOSE header before any key retrieval. Claims are not read here."""
    if (
        type(token) is not str
        or not token
        or len(token) > MAX_TOKEN_CHARS
        or not token.isascii()
    ):
        raise PaymentContextInvalid("MALFORMED_TOKEN")
    parts = token.split(".")
    if len(parts) != 3 or any(_SEGMENT.fullmatch(part) is None for part in parts):
        raise PaymentContextInvalid("MALFORMED_TOKEN")
    try:
        header = jwt.get_unverified_header(token)
    except (InvalidTokenError, ValueError, TypeError):
        raise PaymentContextInvalid("MALFORMED_TOKEN") from None
    if not isinstance(header, dict):
        raise PaymentContextInvalid("MALFORMED_TOKEN")
    if header.get("alg") != ALGORITHM:
        raise PaymentContextInvalid("WRONG_ALGORITHM")
    if TOKEN_KEY_HEADERS.intersection(header):
        raise PaymentContextInvalid("TOKEN_SUPPLIED_KEY_MATERIAL")
    if UNSUPPORTED_HEADERS.intersection(header):
        raise PaymentContextInvalid("UNSUPPORTED_HEADER")
    kid = header.get("kid")
    if kid is not None and type(kid) is not str:
        raise PaymentContextInvalid("MALFORMED_TOKEN")
    return header


class PaymentContextVerifier:
    """Verify ``PAYMENT-CONTEXT`` tokens against one origin URL's payment terms."""

    def __init__(
        self,
        terms: PaymentTerms,
        *,
        resolver: Optional[PaymentKeyResolver] = None,
        leeway: int = DEFAULT_LEEWAY_SECONDS,
    ) -> None:
        if type(leeway) is not int or not 0 <= leeway <= MAX_LEEWAY_SECONDS:
            raise ValueError("payment clock leeway must be whole seconds in [0, 30]")
        self.terms = terms
        self.leeway = leeway
        self._resolver = resolver or PaymentKeyResolver()

    async def verify(self, token: object) -> VerifiedPayment:
        """Return the verified payment, or raise ``PaymentContextInvalid``.

        Raises ``PaymentKeysUnavailable`` when no fresh key set exists. Callers
        must then refuse the request (fail closed), not serve it.
        """
        header = protected_header(token)
        kid = header.get("kid")
        key = await self._resolver.key_for(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=self.terms.audience,
                leeway=self.leeway,
                options={
                    "require": ["exp", "nbf", "iat", "aud"],
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "strict_aud": True,
                },
            )
        except ExpiredSignatureError:
            raise PaymentContextInvalid("EXPIRED") from None
        except ImmatureSignatureError:
            raise PaymentContextInvalid("NOT_YET_VALID") from None
        except InvalidAudienceError:
            raise PaymentContextInvalid("WRONG_AUDIENCE") from None
        except InvalidSignatureError:
            raise PaymentContextInvalid("BAD_SIGNATURE") from None
        except MissingRequiredClaimError:
            raise PaymentContextInvalid("MISSING_CLAIM") from None
        except (PyJWTError, ValueError, TypeError):
            raise PaymentContextInvalid("INVALID_TOKEN") from None
        for name in ("iat", "nbf", "exp"):
            if type(claims.get(name)) is not int:
                raise PaymentContextInvalid("TIME_CLAIMS_INVALID")
        if type(claims.get("aud")) is not str or claims["aud"] != self.terms.audience:
            raise PaymentContextInvalid("WRONG_AUDIENCE")
        if claims.get("scheme") != self.terms.scheme:
            raise PaymentContextInvalid("WRONG_SCHEME")
        try:
            amount = parse_atomic_amount(claims.get("amount"))
        except ValueError as exc:
            raise PaymentContextInvalid(str(exc)) from None
        if amount != self.terms.amount:
            raise PaymentContextInvalid("WRONG_AMOUNT")
        return VerifiedPayment(
            audience=claims["aud"],
            scheme=self.terms.scheme,
            amount=amount,
            iat=claims["iat"],
            nbf=claims["nbf"],
            exp=claims["exp"],
            kid=kid,
            context_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
        )
