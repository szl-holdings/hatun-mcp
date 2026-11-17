"""Fixed-origin owned Cortex proposals, with structural evidence validation.

This is not the product-domain Cloudflare Worker or the generic model gateway.
No signature, proof execution, model quality, durable delivery or action
authority is established here. The upstream proposal remains unsigned.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import re

import httpx

from .backends import BackendResult

ORIGIN = "https://szlholdings-a11oy.hf.space"
CONTRACT_PATH = "/api/v2/governed-contract"
INFER_PATH = "/api/v2/governed-infer"
SCHEMA = "szl.hatun.owned-cortex-proposal/v1"
CONTRACT_SCHEMA = "szl.a11oy.owned-khipu-cortex-contract/v1"
RESPONSE_SCHEMA = "szl.a11oy.owned-khipu-cortex-response/v1"
RECEIPT_SCHEMA = "szl.a11oy.owned-khipu-cortex-receipt/v1"
ERROR_SCHEMA = "szl.a11oy.owned-khipu-cortex-error/v1"
TRACE_SCHEMA = "szl.trace.receipt-observation/v1"
TOTAL_TIMEOUT_SECONDS = 45.0
MAX_CONTRACT_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MODEL = {
    "repository": "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
    "revision": "67d60ec577730747055491640cfb91fc4a4b5d25",
    "filename": "SZL-Khipu-1.5B-Q4_K_M.gguf",
    "sha256": "13c1a1993063e1dff92f7413ccf48eaca6d48efc8801ae9af35961ae3396623a",
}
MODEL_SIZE = 986_047_904
NEMO_REVISION = "810231a531188bb569e3faa17396386eb0a5e260"
LOCKED_FORMULAS = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REV = re.compile(r"[0-9a-f]{40}\Z")

_STAGES = ("PRE_GENERATION", "TEXT_R1_R5", "POST_GENERATION")
_RESPONSE_FIELDS = frozenset("""
schema request_id state decision output output_sha256 source_revision executed
tool_execution authority_state model runtime second_brain evidence_handles
evidence_set_sha256 citations citations_sha256 claims claims_sha256 formula_authority
nemo metrics receipt anatomy_observation honesty trace_observation
""".split())


class BoundaryError(ValueError):
    """Fixed public reason code, without provider or caller text."""


def _require(condition, code="UPSTREAM_CONTRACT_INVALID"):
    if not condition:
        raise BoundaryError(code)


def canonical_bytes(value):
    # Matches Cortex's existing Python serializer; not RFC8785/authentication.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_hash(value, pattern=_SHA):
    return type(value) is str and pattern.fullmatch(value) is not None


def normalize_request(prompt, max_new_tokens, k):
    _require(type(prompt) is str and 1 <= len(prompt) <= 4000, "INVALID_ARGUMENTS")
    _require(type(max_new_tokens) is int and 16 <= max_new_tokens <= 128,
             "INVALID_ARGUMENTS")
    _require(type(k) is int and 1 <= k <= 4, "INVALID_ARGUMENTS")
    prompt = prompt.strip()
    _require(bool(prompt) and "\x00" not in prompt and
             not any(token in prompt for token in ("<|im_start|>", "<|im_end|>", "<s>", "</s>")),
             "INVALID_ARGUMENTS")
    return {"prompt": prompt, "max_new_tokens": max_new_tokens, "k": k}


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "UPSTREAM_JSON_INVALID")
        result[key] = value
    return result


def _constant_rejected(_value):
    raise BoundaryError("UPSTREAM_JSON_INVALID")


async def _read_json(client, method, path, limit, payload=None):
    # The caller cannot supply a URL, model, credential or arbitrary header.
    async with client.stream(method, ORIGIN + path, json=payload) as response:
        status = response.status_code
        _require(not 300 <= status < 400, "UPSTREAM_REDIRECT_REJECTED")
        _require(response.headers.get("content-type", "").split(";")[0].strip().lower()
                 == "application/json", "UPSTREAM_JSON_INVALID")
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            _require(len(raw) + len(chunk) <= limit, "UPSTREAM_RESPONSE_TOO_LARGE")
            raw.extend(chunk)
        try:
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
                              parse_constant=_constant_rejected)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise BoundaryError("UPSTREAM_JSON_INVALID") from exc
        _require(type(body) is dict, "UPSTREAM_JSON_INVALID")
        return status, body, response.headers


def _headers_bound(headers, revision):
    _require(headers.get("x-szl-source-revision") == revision, "SOURCE_REVISION_MISMATCH")
    _require(headers.get("x-szl-governed-inference") == "owned-khipu-v1",
             "UPSTREAM_RUNTIME_MISMATCH")
    _require("no-store" in {part.strip() for part in headers.get("cache-control", "").lower().split(",")},
             "UPSTREAM_FRESHNESS_UNAVAILABLE")
    # Fresh network retrieval is not an attestation of latest GitHub deployment.
    age = headers.get("age")
    _require(age is None or age.strip() == "0", "UPSTREAM_FRESHNESS_UNAVAILABLE")


def _no_authority(body):
    _require(body["executed"] is False and body["tool_execution"] is False
             and body["authority_state"] == "NO_ACTION_AUTHORITY",
             "UPSTREAM_AUTHORITY_MISMATCH")


def _model_bound(body):
    _require(all(body.get(key) == value for key, value in MODEL.items()),
             "MODEL_IDENTITY_MISMATCH")


def _lambda_bound(body):
    _require(body["status"] == "CONJECTURE_1_ADVISORY"
             and body["can_authorize"] is False
             and body["can_be_sole_allow_basis"] is False,
             "UPSTREAM_AUTHORITY_MISMATCH")


def validate_contract(body, headers):
    _require(body["schema"] == CONTRACT_SCHEMA, "UPSTREAM_RUNTIME_MISMATCH")
    revision = body["source_revision"]
    _require(_is_hash(revision, _REV), "SOURCE_REVISION_MISMATCH")
    _headers_bound(headers, revision)
    _require(body["source_repository"] == "szl-holdings/a11oy")
    _require(body["endpoints"]["infer"] == INFER_PATH)
    _model_bound(body["model"])
    _require(body["model"]["kind"] == "OWNED_KHIPU_GGUF_LOCAL_CPU"
             and type(body["model"]["size"]) is int and body["model"]["size"] == MODEL_SIZE)
    authority = body["authority"]
    _require(authority == {"model_authority": "PROPOSAL_ONLY", "tool_execution": False,
                          "autonomous_execution": False, "action_authority": "NONE"},
             "UPSTREAM_AUTHORITY_MISMATCH")
    _require(all(authority[key] is False for key in ("tool_execution", "autonomous_execution")),
             "UPSTREAM_AUTHORITY_MISMATCH")
    brain = body["second_brain"]
    _require(brain["content_access"] == "PUBLIC_PROJECTION_HANDLES_ONLY"
             and brain["private_graph_allowed"] is False)
    formulas = body["formula_authority"]
    _require(type(formulas["locked_proven_count"]) is int
             and formulas["locked_proven_count"] == 8
             and formulas["locked_proven_ids"] == LOCKED_FORMULAS)
    _lambda_bound(formulas["lambda"])
    _require(body["nemo"]["revision"] == NEMO_REVISION)
    receipts = body["receipts"]
    _require(receipts["schema"] == RECEIPT_SCHEMA
             and receipts["signature_status"] == "UNSIGNED_RUNTIME"
             and receipts["persistence"] == "EPHEMERAL_PROCESS_MEMORY_ONLY"
             and receipts["must_be_signed_before_consequential_action"] is True)
    return revision


def _fields(value, names):
    _require(type(value) is dict and set(value) == set(names.split()),
             "UPSTREAM_FIELDS_INVALID")


def _validate_response_shape(body):
    # Closed nested maps prevent an otherwise valid response from smuggling
    # provider diagnostics, private graph content or credential fields.
    _fields(body["model"], "id repository revision filename sha256 size adapter_revision "
                          "tokenizer_revision template_revision ownership")
    model = body["model"]
    _require(model["id"] == MODEL["repository"] + "/" + MODEL["filename"]
             and type(model["size"]) is int and model["size"] == MODEL_SIZE
             and model["adapter_revision"] == "none")
    runtime = body["runtime"]
    _fields(runtime, "engine version library_version hardware_fingerprint device threads")
    _require(runtime["engine"] == "llama-cpp-python" and runtime["device"] == "CPU"
             and type(runtime["threads"]) is int and 1 <= runtime["threads"] <= 4)
    _require(all(type(runtime[key]) is str and 1 <= len(runtime[key]) <= 64
                 for key in ("version", "library_version")))
    _require(type(runtime["hardware_fingerprint"]) is str
             and re.fullmatch(r"sha256:[0-9a-f]{64}", runtime["hardware_fingerprint"]))
    brain = body["second_brain"]
    _fields(brain, "state retrieval node_count content_hash content_access private_graph_present query_latency")
    _require(brain["state"] == "READY" and type(brain["retrieval"]) is str
             and len(brain["retrieval"]) <= 256
             and type(brain["node_count"]) is int and brain["node_count"] >= 0
             and type(brain["content_hash"]) is str
             and re.fullmatch(r"[0-9a-f]{16}", brain["content_hash"]))
    latency = brain["query_latency"]
    _fields(latency, "label value_ms unit clock basis scope excludes")
    _require(latency["label"] == "MEASURED" and latency["unit"] == "milliseconds"
             and latency["clock"] == "time.perf_counter_ns (monotonic)"
             and latency["basis"] == "server-observed elapsed duration for this request"
             and latency["scope"] == "BrainIndex.ask retrieval, graph expansion, community context, and optional sovereign generation"
             and latency["excludes"] == "response serialization, network transport, and browser render time"
             and type(latency["value_ms"]) in (int, float) and 0 <= latency["value_ms"] <= 3_600_000)
    metrics = body["metrics"]
    _fields(metrics, "generation_latency prompt_tokens completion_tokens token_counts_label")
    _fields(metrics["generation_latency"], "label value_ms scope")
    generation = metrics["generation_latency"]
    _require(generation["label"] == "MEASURED"
             and generation["scope"] == "in-process llama.cpp create_chat_completion call"
             and type(generation["value_ms"]) in (int, float) and 0 <= generation["value_ms"] <= 3_600_000)
    _require(metrics["token_counts_label"] in {"MEASURED", "UNAVAILABLE"})
    for key in ("prompt_tokens", "completion_tokens"):
        _require(metrics[key] is None or (type(metrics[key]) is int and 0 <= metrics[key] <= 100000))
    _fields(body["formula_authority"], "locked_proven_count locked_proven_ids applications authorization_basis_ids lambda")
    _fields(body["formula_authority"]["lambda"], "formula_id status can_authorize can_be_sole_allow_basis")
    _require(body["formula_authority"]["lambda"]["formula_id"] == "F23")
    _fields(body["receipt"], "schema payload receipt_sha256 signature persistence prompt_or_evidence_text_persisted")
    _fields(body["receipt"]["signature"], "status durable must_be_signed_before_consequential_action")
    _fields(body["receipt"]["payload"]["model"], "repository revision filename sha256 kind")
    _fields(body["receipt"]["payload"]["nemo"], "revision pre_input_hash text_input_hash post_input_hash")
    for witness in body["nemo"]:
        _fields(witness, "stage decision violated_rules rule_version input_hash reasons")
        # Pinned szl-nemo emits an empty reasons tuple for ALLOW. No free-text
        # reason is required or accepted on a successful proposal.
        _require(witness["reasons"] == [])
        _require(witness["rule_version"] == ("doctrine-v11/R1-R5"
                 if witness["stage"] == "TEXT_R1_R5" else "doctrine-v11/E1-E10"))
    _fields(body["anatomy_observation"], "delivery persistence observer_authority observation_count event")
    _fields(body["honesty"], "output_is_owned_khipu_inference output_is_model_proposal output_is_signed "
                            "action_authority lambda_is_theorem private_chain_of_thought_exposed")
    _require(body["honesty"]["output_is_owned_khipu_inference"] is True)


def _validate_diagnostic(value):
    _fields(value, "schema decision scope authority minimum threshold coverage reason_codes")
    _fields(value["coverage"], "required observed")
    _require(value["schema"] == "szl.trace.diagnostic-minimum/v1"
             and value["scope"] == "STRUCTURAL_DIAGNOSTIC_ONLY"
             and value["authority"] == "NONE" and value["decision"] in {"PASS", "HOLD"},
             "TRACE_CONTRACT_INVALID")
    for key in ("minimum", "threshold"):
        _require(value[key] is None or (type(value[key]) in (int, float) and 0 <= value[key] <= 1),
                 "TRACE_CONTRACT_INVALID")
    _require(all(type(number) is int and 0 <= number <= 8
                 for number in value["coverage"].values()), "TRACE_CONTRACT_INVALID")
    codes = value["reason_codes"]
    _require(type(codes) is list and len(codes) <= 8 and all(
        code in {"INVALID_THRESHOLD", "INVALID_REQUIRED_CHECKS", "INVALID_SCORES",
                 "MISSING_REQUIRED_CHECK", "UNEXPECTED_CHECK", "INVALID_SCORE", "BELOW_THRESHOLD"}
        for code in codes if type(code) is str) and all(type(code) is str for code in codes),
        "TRACE_CONTRACT_INVALID")


def _validate_trace(trace, revision, receipt_sha):
    if trace is None:
        return "ABSENT"
    _require(type(trace) is dict and trace["schema"] == TRACE_SCHEMA
             and trace["authority"] == "NONE"
             and trace["delivery"] == "RESPONSE_SIDECAR_ONLY", "TRACE_CONTRACT_INVALID")
    if "diagnostic" in trace:
        _validate_diagnostic(trace["diagnostic"])
    state = trace["state"]
    _require(state in {"OBSERVED", "UNAVAILABLE"}, "TRACE_CONTRACT_INVALID")
    if state == "UNAVAILABLE":
        _require(set(trace) <= {"schema", "state", "authority", "delivery",
                               "reason_codes", "diagnostic"}, "TRACE_CONTRACT_INVALID")
        _require(type(trace.get("reason_codes")) is list
                 and 1 <= len(trace["reason_codes"]) <= 8
                 and all(type(code) is str and code in {
                     "OBSERVATION_UNAVAILABLE", "STRUCTURAL_CONSISTENCY_HOLD",
                     "TRACE_CONTEXT_UNAVAILABLE", "INVALID_IDENTITY"}
                         for code in trace["reason_codes"]), "TRACE_CONTRACT_INVALID")
        return state
    _require(set(trace) == {
        "schema", "state", "operation", "authority", "signature_status", "persistence",
        "delivery", "collector_delivery", "trace_context_source", "trace_id", "span_id",
        "trace_flags", "receipt_sha256", "model_sha256", "source_revision",
        "diagnostic", "observation_sha256",
    }, "TRACE_CONTRACT_INVALID")
    _require(trace["source_revision"] == revision and trace["receipt_sha256"] == receipt_sha
             and trace["model_sha256"] == MODEL["sha256"], "TRACE_CONTRACT_INVALID")
    _require(trace["operation"] == "governed_inference_proposal"
             and trace["signature_status"] == "UNSIGNED_DERIVED_OBSERVATION"
             and trace["persistence"] == "RESPONSE_ONLY"
             and trace["collector_delivery"] == "UNVERIFIED"
             and trace["trace_context_source"] == "SERVER_MIDDLEWARE", "TRACE_CONTRACT_INVALID")
    for key, length in (("trace_id", 32), ("span_id", 16), ("trace_flags", 2)):
        value = trace[key]
        _require(type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value)
                 and (key == "trace_flags" or int(value, 16) != 0), "TRACE_CONTRACT_INVALID")
    diagnostic = trace["diagnostic"]
    _require(diagnostic == {
        "schema": "szl.trace.diagnostic-minimum/v1", "decision": "PASS",
        "scope": "STRUCTURAL_DIAGNOSTIC_ONLY", "authority": "NONE",
        "minimum": 1.0, "threshold": 1.0, "coverage": {"required": 8, "observed": 8},
        "reason_codes": [],
    } and type(diagnostic["minimum"]) in (int, float)
       and type(diagnostic["threshold"]) in (int, float)
       and all(type(value) is int for value in diagnostic["coverage"].values()),
       "TRACE_CONTRACT_INVALID")
    _require(trace["observation_sha256"] == digest(
        {key: value for key, value in trace.items() if key != "observation_sha256"}),
        "TRACE_DIGEST_MISMATCH")
    return state


def validate_response(body, request, revision, headers):
    _headers_bound(headers, revision)
    _require(set(body) <= _RESPONSE_FIELDS and body["schema"] == RESPONSE_SCHEMA,
             "UPSTREAM_RUNTIME_MISMATCH")
    _require(body["source_revision"] == revision, "SOURCE_REVISION_MISMATCH")
    _validate_response_shape(body)
    _no_authority(body)
    _require(body["state"] == "PROPOSAL" and body["decision"] == "review")
    output = body["output"]
    _require(type(output) is str and 0 < len(output) <= 24000, "OUTPUT_INVALID")
    _require(text_digest(output) == body["output_sha256"], "OUTPUT_DIGEST_MISMATCH")
    _model_bound(body["model"])
    _require(body["model"]["tokenizer_revision"] == MODEL["revision"]
             and body["model"]["template_revision"] == revision
             and body["model"]["ownership"] == "SZL_HOLDINGS_OWNED_ARTIFACT")
    brain = body["second_brain"]
    _require(brain["content_access"] == "PUBLIC_PROJECTION_HANDLES_ONLY"
             and brain["private_graph_present"] is False)
    handles = body["evidence_handles"]
    _require(type(handles) is list and 1 <= len(handles) <= 4)
    for row in handles:
        _require(type(row) is dict and set(row) == {"node_id", "source", "sha256"})
        _require(type(row["node_id"]) is str and 1 <= len(row["node_id"]) <= 160
                 and type(row["source"]) is str and 1 <= len(row["source"]) <= 500
                 and _is_hash(row["sha256"]))
    evidence_sha = digest(handles)
    _require(body["evidence_set_sha256"] == evidence_sha, "EVIDENCE_DIGEST_MISMATCH")
    citations = body["citations"]
    _require(type(citations) is list and len(citations) <= 4
             and len(set(citations)) == len(citations)
             and all(type(cite) is str and cite in {row["node_id"] for row in handles}
                     for cite in citations))
    _require(body["citations_sha256"] == digest(citations), "EVIDENCE_DIGEST_MISMATCH")
    _require(body["claims"] == [{"label": "MODELED", "statement_sha256": body["output_sha256"]}]
             and body["claims_sha256"] == digest(body["claims"]))
    expected_id = digest({
        "source_revision": revision, "prompt_sha256": text_digest(request["prompt"]),
        "evidence_set_sha256": evidence_sha, "model_revision": MODEL["revision"],
        "max_new_tokens": request["max_new_tokens"], "k": request["k"],
    })[:32]
    _require(body["request_id"] == expected_id, "REQUEST_BINDING_MISMATCH")
    receipt = body["receipt"]
    packet = receipt["payload"]
    _require(receipt["schema"] == RECEIPT_SCHEMA and packet["schema"] == RECEIPT_SCHEMA)
    _require(set(packet) == {
        "schema", "request_id", "source_repository", "source_revision", "prompt_sha256",
        "evidence_set_sha256", "output_sha256", "model", "formula_applications",
        "nemo", "decision", "authority_state", "executed", "tool_execution",
    })
    _no_authority(packet)
    _require(packet["request_id"] == expected_id
             and packet["source_repository"] == "szl-holdings/a11oy"
             and packet["source_revision"] == revision
             and packet["prompt_sha256"] == text_digest(request["prompt"])
             and packet["evidence_set_sha256"] == evidence_sha
             and packet["output_sha256"] == body["output_sha256"]
             and packet["decision"] == "REVIEW_PROPOSAL_ONLY", "RECEIPT_BINDING_MISMATCH")
    _model_bound(packet["model"])
    _require(packet["model"]["kind"] == "OWNED_KHIPU_GGUF_LOCAL_CPU")
    _require(receipt["receipt_sha256"] == digest(packet), "RECEIPT_DIGEST_MISMATCH")
    signature = receipt["signature"]
    _require(signature["status"] == "UNSIGNED_RUNTIME" and signature["durable"] is False
             and signature["must_be_signed_before_consequential_action"] is True
             and receipt["persistence"] == "EPHEMERAL_PROCESS_MEMORY_ONLY"
             and receipt["prompt_or_evidence_text_persisted"] is False)
    formulas = body["formula_authority"]
    _require(type(formulas["locked_proven_count"]) is int
             and formulas["locked_proven_count"] == 8
             and formulas["locked_proven_ids"] == LOCKED_FORMULAS
             and formulas["authorization_basis_ids"] == [])
    _lambda_bound(formulas["lambda"])
    applications = formulas["applications"]
    _require(type(applications) is list and len(applications) == 1
             and applications == packet["formula_applications"])
    application = applications[0]
    _require(set(application) == {"formula_id", "applicability", "basis_sha256",
                                 "scope", "can_authorize_action"}
             and application["formula_id"] == "F1" and application["applicability"] == "APPLIES"
             and _is_hash(application["basis_sha256"])
             and application["scope"] == "REPLAY_HASH_DETERMINISM_ONLY"
             and application["can_authorize_action"] is False)
    witnesses = body["nemo"]
    _require(type(witnesses) is list and len(witnesses) == 3)
    _require(packet["nemo"]["revision"] == NEMO_REVISION)
    for stage, hash_key in zip(_STAGES, ("pre_input_hash", "text_input_hash", "post_input_hash")):
        rows = [row for row in witnesses if type(row) is dict and row.get("stage") == stage]
        _require(len(rows) == 1 and rows[0]["decision"] == "ALLOW"
                 and rows[0]["violated_rules"] == [])
        _require(type(rows[0]["input_hash"]) is str
                 and re.fullmatch(r"sha256:[0-9a-f]{64}", rows[0]["input_hash"])
                 and packet["nemo"][hash_key] == rows[0]["input_hash"])
    anatomy = body["anatomy_observation"]
    event = anatomy["event"]
    _require(anatomy["delivery"] == "DELIVERED"
             and anatomy["persistence"] == "EPHEMERAL_PROCESS_MEMORY_ONLY"
             and anatomy["observer_authority"] == "NONE"
             and type(anatomy["observation_count"]) is int and anatomy["observation_count"] > 0)
    _require(event == {
        "schema": "szl.anatomy.ephemeral-owned-inference/v1",
        "request_id": expected_id, "source_revision": revision,
        "prompt_sha256": packet["prompt_sha256"], "evidence_set_sha256": evidence_sha,
        "output_sha256": body["output_sha256"], "receipt_sha256": receipt["receipt_sha256"],
        "model_revision": MODEL["revision"], "raw_prompt_present": False,
        "raw_evidence_present": False, "raw_output_present": False,
        "private_reasoning_present": False, "private_graph_present": False,
        "observer_authority": "NONE",
    } and all(event[key] is False for key in (
        "raw_prompt_present", "raw_evidence_present", "raw_output_present",
        "private_reasoning_present", "private_graph_present")))
    honesty = body["honesty"]
    _require(honesty["output_is_model_proposal"] is True
             and honesty["output_is_signed"] is False and honesty["action_authority"] is False
             and honesty["lambda_is_theorem"] is False
             and honesty["private_chain_of_thought_exposed"] is False)
    return _validate_trace(body.get("trace_observation"), revision, receipt["receipt_sha256"])


_UPSTREAM_ERRORS = frozenset("""
owned_model_artifact_missing owned_model_size_mismatch owned_model_sha256_mismatch
formula_locked_set_drift formula_locked_count_drift lambda_authority_drift
nemo_version_drift nemo_locked_set_drift source_revision_unavailable
second_brain_returned_no_grounding second_brain_returned_no_usable_handles
owned_model_returned_empty_output owned_model_response_invalid owned_model_attempted_tool_call
owned_model_reasoning_boundary_invalid
owned_model_evidence_handle_invalid owned_model_busy owned_model_citation_not_in_evidence
owned_model_evidence_citation_missing unsafe_anatomy_observation nemo_pre_generation_blocked
nemo_text_witness_blocked nemo_post_generation_blocked
""".split())
_UPSTREAM_EXCEPTION_PREFIXES = frozenset({
    "formula_authority_unavailable", "nemo_unavailable", "owned_model_runtime_unavailable",
    "second_brain_unavailable", "owned_model_generation_failed",
})


def _validated_error(body):
    if body.get("schema") != ERROR_SCHEMA:
        return None
    _require(set(body) <= {"schema", "error", "state", "executed", "tool_execution",
                          "authority_state", "nemo_witness"})
    _no_authority(body)
    _require(body["state"] == "UNAVAILABLE" and type(body["error"]) is str)
    code = body["error"]
    if code not in _UPSTREAM_ERRORS:
        prefix, separator, _suffix = code.partition(":")
        if not separator or prefix not in _UPSTREAM_EXCEPTION_PREFIXES:
            return None  # Keep HTTP status, never echo arbitrary provider text.
        body = {**body, "error": prefix}  # Exception class/suffix is not public evidence.
    if "nemo_witness" in body:
        witness = body["nemo_witness"]
        _require(type(witness) is dict and set(witness) == {
            "stage", "decision", "violated_rules", "rule_version", "input_hash"})
        _require(witness["stage"] in _STAGES and witness["decision"] in {"BLOCK", "REVIEW", "UNAVAILABLE"}
                 and witness["rule_version"] in {
                     "doctrine-v11/R1-R5", "doctrine-v11/E1-E10", "UNAVAILABLE"})
        _require(witness["input_hash"] is None or (type(witness["input_hash"]) is str
                 and re.fullmatch(r"sha256:[0-9a-f]{64}", witness["input_hash"])))
        _require(type(witness["violated_rules"]) is list and len(witness["violated_rules"]) <= 10
                 and all(type(rule) is str and re.fullmatch(r"(?:R[1-5]|E(?:[1-9]|10))", rule)
                         for rule in witness["violated_rules"]))
    return body


def _result(state, reason, *, upstream=None, status=None, revision=None,
            trace_state=None, preflight=False, phase="REQUEST_VALIDATION"):
    endpoint = (ORIGIN + INFER_PATH if phase == "INFERENCE" else
                ORIGIN + CONTRACT_PATH if phase == "CONTRACT_PREFLIGHT" else
                "local://owned-cortex-request")
    data = {
        "schema": SCHEMA, "state": state,
        "phase": phase, "last_http_endpoint": endpoint if status is not None else None,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_revision": revision, "upstream_http_status": status,
        "verification": {
            "scope": "STRUCTURAL_CONSISTENCY_ONLY",
            "signature_verification": "NOT_PERFORMED",
            "freshness": "REQUEST_PREFLIGHT_BOUND" if preflight else "UNAVAILABLE",
            "latest_deployment_verified": False,
            "trace_state": trace_state,
            "anatomy_delivery_scope": "OWNED_CORTEX_PROCESS_MEMORY" if state == "PROPOSAL" else "UNAVAILABLE",
        },
        "upstream": upstream, "reason_codes": [reason] if reason else [],
    }
    return BackendResult(
        deployed=status is not None, http_status=status, endpoint=endpoint,
        error=None if state == "PROPOSAL" else (reason or "UPSTREAM_UNAVAILABLE"),
        data=data, evidence_state=state, evidence_schema=SCHEMA,
        evidence_digest_sha256=digest(data),
    )


async def infer(prompt, max_new_tokens=64, k=3):
    revision = None
    status = None
    preflight = False
    phase = "REQUEST_VALIDATION"
    try:
        request = normalize_request(prompt, max_new_tokens, k)
        phase = "CONTRACT_PREFLIGHT"
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(40.0, connect=5.0), follow_redirects=False,
                trust_env=False, headers={"accept": "application/json",
                                         "cache-control": "no-cache",
                                         "user-agent": "hatun-owned-cortex/1"},
            ) as client:
                status, contract, headers = await _read_json(
                    client, "GET", CONTRACT_PATH, MAX_CONTRACT_BYTES)
                if status != 200:
                    return _result("UNAVAILABLE", "CONTRACT_UNAVAILABLE", status=status,
                                   upstream=_validated_error(contract), phase=phase)
                revision = validate_contract(contract, headers)
                preflight = True
                phase = "INFERENCE"
                status = None  # The preflight status is not an inference response.
                status, body, headers = await _read_json(
                    client, "POST", INFER_PATH, MAX_RESPONSE_BYTES, request)
                if status != 200:
                    _headers_bound(headers, revision)
                    return _result("REJECTED" if status == 422 else "UNAVAILABLE",
                                   "UPSTREAM_DECLINED" if status == 422 else "UPSTREAM_UNAVAILABLE",
                                   upstream=_validated_error(body), status=status,
                                   revision=revision, preflight=preflight, phase=phase)
                trace_state = validate_response(body, request, revision, headers)
                return _result("PROPOSAL", None, upstream=body, status=status,
                               revision=revision, trace_state=trace_state, preflight=True, phase=phase)
    except BoundaryError as exc:
        return _result("REJECTED" if str(exc) == "INVALID_ARGUMENTS" else "UNAVAILABLE",
                       str(exc), status=status, revision=revision, preflight=False, phase=phase)
    except (TimeoutError, httpx.TimeoutException):
        return _result("UNAVAILABLE", "UPSTREAM_TIMEOUT", status=status, revision=revision, phase=phase)
    except httpx.HTTPError:
        return _result("UNAVAILABLE", "UPSTREAM_TRANSPORT_ERROR", status=status, revision=revision, phase=phase)
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
        return _result("UNAVAILABLE", "UPSTREAM_CONTRACT_INVALID",
                       status=status, revision=revision, preflight=False, phase=phase)
