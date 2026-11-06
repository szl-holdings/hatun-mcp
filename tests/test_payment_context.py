"""Hermetic tests for hatun_mcp.payment_context (Cloudflare x402 PAYMENT-CONTEXT).

Every key here is generated in memory for the test. No request reaches
payments.cloudflare.com, no wallet is used and nothing is charged. The JWKS
responses are SIMULATED. Passing these tests shows how the verifier behaves on
these inputs. It does not show that Cloudflare's live tokens use this exact
shape; that needs one controlled paid canary.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest

os.environ.setdefault("HATUN_MCP_DISABLE_DYNAMIC", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from hatun_mcp import payment_context as pc  # noqa: E402

AUDIENCE = "https://mcp.example.test/mcp/"
AMOUNT = 10_000
MISSING = object()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64json(value) -> str:
    return b64url(json.dumps(value, separators=(",", ":")).encode())


class Signer:
    """An in-memory Ed25519 key standing in for a Cloudflare signing key."""

    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self.private = Ed25519PrivateKey.generate()
        raw = self.private.public_key().public_bytes_raw()
        self.jwk = {"kty": "OKP", "crv": "Ed25519", "x": b64url(raw),
                    "kid": kid, "alg": "EdDSA", "use": "sig"}

    def token(self, *, headers=None, kid=MISSING, **claims) -> str:
        now = int(time.time())
        body = {"iat": now - 1, "nbf": now - 1, "exp": now + 120,
                "aud": AUDIENCE, "scheme": "exact", "amount": str(AMOUNT)}
        body.update(claims)
        body = {k: v for k, v in body.items() if v is not MISSING}
        header = {"kid": self.kid if kid is MISSING else kid, **(headers or {})}
        if header["kid"] is None:
            header.pop("kid")
        return jwt.encode(body, self.private, algorithm="EdDSA", headers=header)


def jwks(keys, *, cache="max-age=300", status=200, content_type="application/json",
         url=pc.JWKS_URL, extra=None, body=None):
    headers = {"content-type": content_type, **(extra or {})}
    if cache is not None:
        headers["cache-control"] = cache
    payload = body if body is not None else json.dumps({"keys": keys}).encode()
    return pc.JwksResponse(status=status, headers=httpx.Headers(headers), body=payload, url=url)


class FakeFetch:
    """Counts JWKS retrievals; ``respond(call_number)`` returns or raises."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        result = self.respond(self.calls)
        if isinstance(result, BaseException):
            raise result
        if asyncio.iscoroutine(result):
            result = await result
        return result


class Clock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def make(fetch, *, clock=time.time, scheme="exact", amount=AMOUNT, leeway=pc.DEFAULT_LEEWAY_SECONDS):
    terms = pc.PaymentTerms(audience=AUDIENCE, scheme=scheme, amount=amount)
    return pc.PaymentContextVerifier(
        terms, resolver=pc.PaymentKeyResolver(fetch=fetch, clock=clock), leeway=leeway,
    )


def run(verifier, token):
    return asyncio.run(verifier.verify(token))


class PaymentContextTokenTests(unittest.TestCase):
    def setUp(self):
        self.signer = Signer("k1")
        self.fetch = FakeFetch(lambda _: jwks([self.signer.jwk]))
        self.verifier = make(self.fetch)

    def reason(self, token, verifier=None):
        with self.assertRaises(pc.PaymentContextInvalid) as caught:
            run(verifier or self.verifier, token)
        return caught.exception.reason

    def test_valid_exact_token_is_verified_against_the_pinned_jwks(self):
        token = self.signer.token()
        payment = run(self.verifier, token)
        self.assertEqual(payment.audience, AUDIENCE)
        self.assertEqual((payment.scheme, payment.amount, payment.kid), ("exact", AMOUNT, "k1"))
        self.assertEqual(payment.context_sha256, hashlib.sha256(token.encode()).hexdigest())
        fields = payment.receipt_fields()
        self.assertEqual(fields["jwks"], "https://payments.cloudflare.com/certs")
        self.assertEqual(fields["authorized_amount_atomic"], "10000")
        self.assertIs(fields["settlement_evidence"], False)
        self.assertNotIn(token, json.dumps(fields))
        self.assertEqual(self.fetch.calls, 1)

    def test_valid_upto_token_carries_the_authorized_maximum(self):
        verifier = make(self.fetch, scheme="upto")
        payment = run(verifier, self.signer.token(scheme="upto"))
        self.assertEqual((payment.scheme, payment.amount), ("upto", AMOUNT))

    def test_expired_token_is_refused_with_a_bounded_leeway(self):
        now = int(time.time())
        self.assertEqual(self.reason(self.signer.token(exp=now - 60)), "EXPIRED")
        # Two seconds late is inside the 5 s leeway; 20 s late is not.
        run(self.verifier, self.signer.token(exp=now - 2))
        self.assertEqual(self.reason(self.signer.token(exp=now - 20)), "EXPIRED")
        strict = make(self.fetch, leeway=0)
        self.assertEqual(self.reason(self.signer.token(exp=now - 2), strict), "EXPIRED")

    def test_future_nbf_or_iat_is_not_yet_valid(self):
        now = int(time.time())
        self.assertEqual(self.reason(self.signer.token(nbf=now + 60)), "NOT_YET_VALID")
        self.assertEqual(self.reason(self.signer.token(iat=now + 60)), "NOT_YET_VALID")
        run(self.verifier, self.signer.token(nbf=now + 2, iat=now + 2))

    def test_audience_must_equal_the_exact_host_and_path(self):
        for audience in ("https://evil.example.test/mcp/", "http://mcp.example.test/mcp/",
                         "https://mcp.example.test/mcp", "https://mcp.example.test/mcp/x",
                         "https://mcp.example.test/mcp/?q=1", "https://MCP.example.test/mcp/",
                         "https://mcp.example.test:8443/mcp/", [AUDIENCE]):
            with self.subTest(audience=audience):
                self.assertEqual(self.reason(self.signer.token(aud=audience)), "WRONG_AUDIENCE")
        for audience in (MISSING, ""):
            self.assertEqual(self.reason(self.signer.token(aud=audience)), "MISSING_CLAIM")

    def test_bad_signatures_are_refused(self):
        token = self.signer.token()
        head, payload, signature = token.split(".")
        flipped = bytearray(base64.urlsafe_b64decode(signature + "=="))
        flipped[0] ^= 1
        self.assertEqual(self.reason(f"{head}.{payload}.{b64url(bytes(flipped))}"), "BAD_SIGNATURE")
        cheaper = b64json({**jwt.decode(token, options={"verify_signature": False}), "amount": "1000"})
        self.assertEqual(self.reason(f"{head}.{cheaper}.{signature}"), "BAD_SIGNATURE")
        impostor = Signer("k1")  # same kid, different private key
        self.assertEqual(self.reason(impostor.token()), "BAD_SIGNATURE")

    def test_amount_must_equal_the_configured_price(self):
        self.assertEqual(self.reason(self.signer.token(amount="1000")), "WRONG_AMOUNT")
        self.assertEqual(self.reason(self.signer.token(amount="100000")), "WRONG_AMOUNT")
        for value in (10000, "010000", "1e4", " 10000", "", None, MISSING, ["10000"]):
            with self.subTest(amount=value):
                self.assertEqual(self.reason(self.signer.token(amount=value)), "MALFORMED_AMOUNT")
        for value in ("999", "100000001", "1" + "0" * 5000):
            with self.subTest(amount=value[:12]):
                self.assertEqual(self.reason(self.signer.token(amount=value)), "AMOUNT_OUT_OF_BOUNDS")

    def test_scheme_must_equal_the_configured_scheme(self):
        for scheme in ("upto", "EXACT", ["exact"], None, MISSING):
            with self.subTest(scheme=scheme):
                self.assertEqual(self.reason(self.signer.token(scheme=scheme)), "WRONG_SCHEME")
        upto = make(self.fetch, scheme="upto")
        self.assertEqual(self.reason(self.signer.token(scheme="exact"), upto), "WRONG_SCHEME")

    def test_time_claims_must_be_integers(self):
        now = int(time.time())
        for claim, value in (("exp", str(now + 60)), ("exp", now + 60.5), ("iat", True),
                             ("nbf", float(now - 1))):
            with self.subTest(claim=claim, value=value):
                self.assertIn(self.reason(self.signer.token(**{claim: value})),
                              {"TIME_CLAIMS_INVALID", "INVALID_TOKEN"})
        self.assertEqual(self.reason(self.signer.token(exp=MISSING)), "MISSING_CLAIM")

    def test_unsafe_or_malformed_tokens_never_trigger_key_retrieval(self):
        claims = b64json({"aud": AUDIENCE, "scheme": "exact", "amount": str(AMOUNT)})
        hs256 = jwt.encode({"aud": AUDIENCE}, "s" * 32, algorithm="HS256")
        es256 = jwt.encode({"aud": AUDIENCE}, generate_private_key(SECP256R1()), algorithm="ES256")
        cases = {
            "MALFORMED_TOKEN": [None, 7, "", "not-a-jwt", "a.b", "a.b.c.d", "x" * 9000,
                                self.signer.token() + "é", f"{b64json({'alg': 'none'})}.{claims}.",
                                f"{b64json({'alg': 'EdDSA', 'kid': 5})}.{claims}.AAAA",
                                f"{b64json(['EdDSA'])}.{claims}.AAAA", f"{claims}=.{claims}.AAAA",
                                f"{b64json({'alg': 'EdDSA', 'crit': ['b64'], 'b64': False})}.{claims}.AAAA",
                                f"{b64json({'alg': 'EdDSA', 'crit': ['exp']})}.{claims}.AAAA"],
            "WRONG_ALGORITHM": [hs256, es256, f"{b64json({'alg': 'none'})}.{claims}.AAAA",
                                f"{b64json({'alg': 'Ed448'})}.{claims}.AAAA"],
            "TOKEN_SUPPLIED_KEY_MATERIAL": [
                self.signer.token(headers={"jku": "https://attacker.invalid/keys"}),
                self.signer.token(headers={"x5u": "https://attacker.invalid/cert"}),
                self.signer.token(headers={"jwk": self.signer.jwk}),
                self.signer.token(headers={"x5c": []}),
            ],
            "UNSUPPORTED_HEADER": [f"{b64json({'alg': 'EdDSA', 'crit': ['b64'], 'b64': True})}.{claims}.AAAA"],
        }
        for reason, tokens in cases.items():
            for token in tokens:
                with self.subTest(reason=reason, token=str(token)[:40]):
                    self.assertEqual(self.reason(token), reason)
        self.assertEqual(self.fetch.calls, 0)

    def test_kidless_token_is_accepted_only_against_a_single_key_set(self):
        run(self.verifier, self.signer.token(kid=None))
        other = Signer("k2")
        both = make(FakeFetch(lambda _: jwks([self.signer.jwk, other.jwk])))
        self.assertEqual(self.reason(self.signer.token(kid=None), both), "UNKNOWN_KEY")
        run(both, other.token())
        twin = make(FakeFetch(lambda _: jwks([self.signer.jwk, {**other.jwk, "kid": "k1"}])))
        self.assertEqual(self.reason(self.signer.token(), twin), "UNKNOWN_KEY")


class PaymentKeyResolverTests(unittest.TestCase):
    def setUp(self):
        self.first = Signer("first")
        self.second = Signer("second")

    def unavailable(self, verifier, token):
        with self.assertRaises(pc.PaymentKeysUnavailable) as caught:
            run(verifier, token)
        return caught.exception.reason

    def test_jwks_outage_or_invalid_key_sets_fail_closed(self):
        good = self.first.jwk
        cases = [
            ("PAYMENT_KEYS_FETCH_FAILED", OSError("network unreachable")),
            ("PAYMENT_KEYS_FETCH_FAILED", TimeoutError()),
            ("PAYMENT_KEYS_FETCH_FAILED", httpx.ConnectError("refused")),
            ("PAYMENT_KEYS_RESPONSE_INVALID", jwks([good], status=503)),
            ("PAYMENT_KEYS_RESPONSE_INVALID", jwks([good], status=302)),
            ("PAYMENT_KEYS_RESPONSE_INVALID", jwks([good], url="https://attacker.invalid/certs")),
            ("PAYMENT_KEYS_CONTENT_TYPE_INVALID", jwks([good], content_type="text/html")),
            ("PAYMENT_KEYS_CONTENT_TYPE_INVALID", jwks([good], content_type="application/jsonp")),
            ("PAYMENT_KEYS_BODY_TOO_LARGE", jwks([good], body=b" " * (pc.MAX_JWKS_BYTES + 1))),
            ("PAYMENT_KEYS_SET_INVALID", jwks([good], body=b"{")),
            ("PAYMENT_KEYS_SET_INVALID", jwks([good], body=b"null")),
            ("PAYMENT_KEYS_SET_INVALID", jwks([good], body=b"\xff\xfe")),
            ("PAYMENT_KEYS_SET_INVALID", jwks([])),
            ("PAYMENT_KEYS_SET_INVALID", jwks([good] * (pc.MAX_JWKS_KEYS + 1))),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "x": "invalid"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "d": "private-material"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "alg": "ES256"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "use": "enc"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "key_ops": ["sign"]}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "kid": 1}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{**good, "kty": "RSA"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", jwks([{
                **good, "crv": "Ed448",
                "x": b64url(Ed448PrivateKey.generate().public_key().public_bytes_raw())}])),
        ]
        for reason, response in cases:
            with self.subTest(reason=reason, response=repr(response)[:60]):
                fetch = FakeFetch(lambda _, response=response: response)
                self.assertEqual(self.unavailable(make(fetch), self.first.token()), reason)

    def test_expired_keys_are_never_reused_when_the_refetch_fails(self):
        clock = Clock()
        fetch = FakeFetch(lambda call: OSError("offline") if call == 2
                          else jwks([self.first.jwk], cache="max-age=1"))
        verifier = make(fetch, clock=clock)
        token = self.first.token()
        run(verifier, token)
        clock.now += 1
        self.assertEqual(self.unavailable(verifier, token), "PAYMENT_KEYS_FETCH_FAILED")
        self.assertEqual(fetch.calls, 2)
        run(verifier, token)  # recovery fetch is allowed
        self.assertEqual(fetch.calls, 3)

    def test_cache_control_freshness_uses_age_and_refreshes_at_expiry(self):
        clock = Clock()
        fetch = FakeFetch(lambda _: jwks([self.first.jwk], cache="max-age=60", extra={"age": "50"}))
        verifier = make(fetch, clock=clock)
        token = self.first.token()
        run(verifier, token)
        clock.now += 9.999
        run(verifier, token)
        self.assertEqual(fetch.calls, 1)
        clock.now += 0.001
        run(verifier, token)
        self.assertEqual(fetch.calls, 2)

    def test_date_header_and_retrieval_delay_reduce_freshness(self):
        clock = Clock(1_770_000_000.0)

        def respond(_):
            sent = clock.now - 55
            clock.now += 2  # retrieval delay
            return jwks([self.first.jwk], cache="max-age=60",
                        extra={"date": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(sent))})

        fetch = FakeFetch(respond)
        verifier = make(fetch, clock=clock)
        token = self.first.token()
        run(verifier, token)
        clock.now += 2.999
        run(verifier, token)
        self.assertEqual(fetch.calls, 1)
        clock.now += 0.001
        run(verifier, token)
        self.assertEqual(fetch.calls, 2)

    def test_uncacheable_responses_are_fetched_per_verification(self):
        for cache, extra in (("max-age=0", {}), ("max-age=60, no-cache", {}),
                             ("max-age=60, no-store", {}), (None, {}), ("", {}),
                             ("max-age=garbage", {}), ("max-age=60, max-age=600", {}),
                             ("max-age=60", {"age": "60"}), ("max-age=60", {"age": "soon"})):
            with self.subTest(cache=cache, extra=extra):
                fetch = FakeFetch(lambda _, c=cache, e=extra: jwks([self.first.jwk], cache=c, extra=e))
                verifier = make(fetch, clock=Clock())
                token = self.first.token()
                run(verifier, token)
                run(verifier, token)
                self.assertEqual(fetch.calls, 2)

    def test_quoted_max_age_is_honored_and_reuse_is_capped_at_one_day(self):
        clock = Clock()
        fetch = FakeFetch(lambda _: jwks([self.first.jwk], cache='public, max-age="31536000"'))
        verifier = make(fetch, clock=clock)
        token = self.first.token()
        run(verifier, token)
        clock.now += pc.MAX_KEY_CACHE_SECONDS - 1
        run(verifier, token)
        self.assertEqual(fetch.calls, 1)
        clock.now += 1
        run(verifier, token)
        self.assertEqual(fetch.calls, 2)

    def test_unknown_kid_forces_at_most_one_refresh_per_interval(self):
        clock = Clock()
        fetch = FakeFetch(lambda call: jwks([self.first.jwk] if call == 1
                                            else [self.first.jwk, self.second.jwk]))
        verifier = make(fetch, clock=clock)
        run(verifier, self.first.token())
        with self.assertRaises(pc.PaymentContextInvalid) as caught:
            run(verifier, self.second.token())
        self.assertEqual(caught.exception.reason, "UNKNOWN_KEY")
        self.assertEqual(fetch.calls, 1)  # no refetch inside the interval
        clock.now += pc.UNKNOWN_KID_REFRESH_SECONDS
        run(verifier, self.second.token())  # rotation picked up by one forced refresh
        self.assertEqual(fetch.calls, 2)
        stranger = Signer("third")
        for _ in range(5):
            with self.assertRaises(pc.PaymentContextInvalid):
                run(verifier, stranger.token())
        self.assertEqual(fetch.calls, 2)

    def test_rotation_removes_the_old_signer_after_expiry(self):
        clock = Clock()
        fetch = FakeFetch(lambda call: jwks([self.first.jwk if call == 1 else self.second.jwk],
                                            cache="max-age=1"))
        verifier = make(fetch, clock=clock)
        run(verifier, self.first.token())
        clock.now += 1
        with self.assertRaises(pc.PaymentContextInvalid):
            run(verifier, self.first.token())
        run(verifier, self.second.token())
        self.assertEqual(fetch.calls, 2)

    def test_concurrent_verifications_share_one_retrieval(self):
        for cache in ("max-age=300", "no-store"):
            with self.subTest(cache=cache):
                async def scenario():
                    release = asyncio.Event()

                    async def slow():
                        await release.wait()
                        return jwks([self.first.jwk], cache=cache)

                    fetch = FakeFetch(lambda _: slow())
                    verifier = make(fetch, clock=Clock())
                    token = self.first.token()
                    pending = [asyncio.ensure_future(verifier.verify(token)) for _ in range(5)]
                    await asyncio.sleep(0)
                    release.set()
                    results = await asyncio.gather(*pending)
                    self.assertEqual({r.context_sha256 for r in results},
                                     {hashlib.sha256(token.encode()).hexdigest()})
                    self.assertEqual(fetch.calls, 1)
                    await verifier.verify(token)
                    return fetch.calls

                calls = asyncio.run(scenario())
                self.assertEqual(calls, 1 if cache == "max-age=300" else 2)

    def test_default_fetch_is_pinned_unredirected_and_bounded(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(302, headers={"location": "https://attacker.invalid/certs"})

        response = asyncio.run(pc.fetch_pinned_jwks(transport=httpx.MockTransport(handler)))
        self.assertEqual(len(seen), 1)
        self.assertEqual((seen[0].method, str(seen[0].url)), ("GET", pc.JWKS_URL))
        self.assertEqual(seen[0].headers["accept"], "application/json")
        self.assertEqual(response.status, 302)  # not followed
        with self.assertRaises(pc.PaymentKeysUnavailable):
            pc.parse_jwks(response)

        def huge(request):
            return httpx.Response(200, headers={"content-type": "application/json"},
                                  content=b" " * (4 * pc.MAX_JWKS_BYTES))

        response = asyncio.run(pc.fetch_pinned_jwks(transport=httpx.MockTransport(huge)))
        self.assertEqual(len(response.body), pc.MAX_JWKS_BYTES + 1)
        with self.assertRaises(pc.PaymentKeysUnavailable) as caught:
            pc.parse_jwks(response)
        self.assertEqual(caught.exception.reason, "PAYMENT_KEYS_BODY_TOO_LARGE")

        def good(request):
            return httpx.Response(200, headers={"content-type": "application/jwk-set+json"},
                                  json={"keys": [self.first.jwk]})

        response = asyncio.run(pc.fetch_pinned_jwks(transport=httpx.MockTransport(good)))
        by_kid, keys = pc.parse_jwks(response)
        self.assertEqual((list(by_kid), len(keys)), (["first"], 1))


class SettlementAndTermsTests(unittest.TestCase):
    def test_settlement_header_follows_the_documented_scheme(self):
        value = pc.settlement_header_value
        self.assertIsNone(value(scheme="exact", status_code=200, actual=AMOUNT, authorized=AMOUNT))
        self.assertEqual(value(scheme="upto", status_code=200, actual=0, authorized=AMOUNT),
                         '{"amount":"0"}')
        self.assertEqual(value(scheme="upto", status_code=202, actual=AMOUNT, authorized=AMOUNT),
                         '{"amount":"10000"}')
        for status in (400, 403, 500, 503):
            self.assertIsNone(value(scheme="upto", status_code=status, actual=AMOUNT, authorized=AMOUNT))
        for kwargs in ({"actual": AMOUNT + 1}, {"actual": -1}, {"actual": "1"},
                       {"status_code": "200"}, {"scheme": "free"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    value(**{"scheme": "upto", "status_code": 200, "actual": 0,
                             "authorized": AMOUNT, **kwargs})

    def test_terms_and_leeway_are_bounded(self):
        for kwargs in ({"scheme": "free"}, {"amount": 999}, {"amount": 100_000_001},
                       {"amount": "10000"}, {"amount": True}, {"audience": "mcp.example.test/mcp/"},
                       {"audience": "https://mcp.example.test/ mcp/"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    pc.PaymentTerms(**{"audience": AUDIENCE, "scheme": "exact", "amount": AMOUNT, **kwargs})
        terms = pc.PaymentTerms(audience=AUDIENCE, scheme="exact", amount=AMOUNT)
        for leeway in (-1, 31, 5.0, True):
            with self.subTest(leeway=leeway):
                with self.assertRaises(ValueError):
                    pc.PaymentContextVerifier(terms, leeway=leeway)

    def test_admission_counts_only_one_successful_governed_call(self):
        payment = pc.VerifiedPayment(AUDIENCE, "upto", AMOUNT, 1, 1, 2, "k1", "a" * 64)
        admission = pc.PaymentAdmission(payment)
        self.assertFalse(admission.succeeded("szl_formula_evaluate"))
        admission.record(tool="szl_formula_evaluate", status="success")
        self.assertTrue(admission.succeeded("szl_formula_evaluate"))
        self.assertFalse(admission.succeeded("szl_yuyay_score"))
        admission.record(tool="szl_formula_evaluate", status="success")
        self.assertFalse(admission.succeeded("szl_formula_evaluate"))


if __name__ == "__main__":
    unittest.main()
