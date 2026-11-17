"""Deterministic offline Cortex evidence; not a live model/quality witness.

Shape derived from a11oy_governed_cortex.py and vsp_otel/trace_ir.py at
a11oy 4f06ec36c6af629c16b537b7bc9b92269e595658. Test digests use an
independent standard-library serializer, not the adapter's digest function.
"""
import hashlib
import json

REVISION = "a" * 40
MODEL_REVISION = "67d60ec577730747055491640cfb91fc4a4b5d25"
MODEL_HASH = "13c1a1993063e1dff92f7413ccf48eaca6d48efc8801ae9af35961ae3396623a"
MODEL = {"repository": "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
         "revision": MODEL_REVISION, "filename": "SZL-Khipu-1.5B-Q4_K_M.gguf",
         "sha256": MODEL_HASH}
LOCKED = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]
LAMBDA = {"formula_id": "F23", "status": "CONJECTURE_1_ADVISORY",
          "can_authorize": False, "can_be_sole_allow_basis": False}
NEMO = "810231a531188bb569e3faa17396386eb0a5e260"
HEADERS = {"content-type": "application/json", "cache-control": "no-store",
           "x-szl-source-revision": REVISION, "x-szl-governed-inference": "owned-khipu-v1"}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def contract():
    return {
        "schema": "szl.a11oy.owned-khipu-cortex-contract/v1",
        "source_repository": "szl-holdings/a11oy", "source_revision": REVISION,
        "endpoints": {"infer": "/api/v2/governed-infer"},
        "model": {**MODEL, "kind": "OWNED_KHIPU_GGUF_LOCAL_CPU", "size": 986047904},
        "authority": {"model_authority": "PROPOSAL_ONLY", "tool_execution": False,
                      "autonomous_execution": False, "action_authority": "NONE"},
        "second_brain": {"content_access": "PUBLIC_PROJECTION_HANDLES_ONLY",
                         "private_graph_allowed": False},
        "formula_authority": {"locked_proven_count": 8, "locked_proven_ids": LOCKED[:],
                              "lambda": dict(LAMBDA)},
        "nemo": {"revision": NEMO},
        "receipts": {"schema": "szl.a11oy.owned-khipu-cortex-receipt/v1",
                     "signature_status": "UNSIGNED_RUNTIME",
                     "persistence": "EPHEMERAL_PROCESS_MEMORY_ONLY",
                     "must_be_signed_before_consequential_action": True},
    }


def proposal(prompt="Explain the public doctrine.", max_new_tokens=64, k=3, trace_state="OBSERVED"):
    prompt = prompt.strip()
    output = "The public source describes a proposal, with no action authority. [doctrine:F1]"
    handles = [{"node_id": "doctrine:F1", "source": "public:doctrine", "sha256": "b" * 64}]
    evidence_sha = sha(handles)
    output_sha = text_sha(output)
    prompt_sha = text_sha(prompt)
    request_id = sha({"source_revision": REVISION, "prompt_sha256": prompt_sha,
                     "evidence_set_sha256": evidence_sha, "model_revision": MODEL_REVISION,
                     "max_new_tokens": max_new_tokens, "k": k})[:32]
    applications = [{"formula_id": "F1", "applicability": "APPLIES", "basis_sha256": "c" * 64,
                     "scope": "REPLAY_HASH_DETERMINISM_ONLY", "can_authorize_action": False}]
    nemo = [{"stage": stage, "decision": "ALLOW", "violated_rules": [],
             "rule_version": "doctrine-v11/R1-R5" if stage == "TEXT_R1_R5" else "doctrine-v11/E1-E10",
             "input_hash": "sha256:" + char * 64, "reasons": []}
            for stage, char in zip(("PRE_GENERATION", "TEXT_R1_R5", "POST_GENERATION"), "def")]
    packet = {
        "schema": "szl.a11oy.owned-khipu-cortex-receipt/v1", "request_id": request_id,
        "source_repository": "szl-holdings/a11oy", "source_revision": REVISION,
        "prompt_sha256": prompt_sha, "evidence_set_sha256": evidence_sha, "output_sha256": output_sha,
        "model": {**MODEL, "kind": "OWNED_KHIPU_GGUF_LOCAL_CPU"},
        "formula_applications": applications,
        "nemo": {"revision": NEMO, **dict(zip(("pre_input_hash", "text_input_hash", "post_input_hash"),
                                            (row["input_hash"] for row in nemo)))},
        "decision": "REVIEW_PROPOSAL_ONLY", "authority_state": "NO_ACTION_AUTHORITY",
        "executed": False, "tool_execution": False,
    }
    receipt_sha = sha(packet)
    event = {
        "schema": "szl.anatomy.ephemeral-owned-inference/v1", "request_id": request_id,
        "source_revision": REVISION, "prompt_sha256": prompt_sha, "evidence_set_sha256": evidence_sha,
        "output_sha256": output_sha, "receipt_sha256": receipt_sha, "model_revision": MODEL_REVISION,
        "raw_prompt_present": False, "raw_evidence_present": False, "raw_output_present": False,
        "private_reasoning_present": False, "private_graph_present": False, "observer_authority": "NONE",
    }
    claims = [{"label": "MODELED", "statement_sha256": output_sha}]
    result = {
        "schema": "szl.a11oy.owned-khipu-cortex-response/v1", "request_id": request_id,
        "state": "PROPOSAL", "decision": "review", "output": output, "output_sha256": output_sha,
        "source_revision": REVISION, "executed": False, "tool_execution": False,
        "authority_state": "NO_ACTION_AUTHORITY",
        "model": {**MODEL, "id": MODEL["repository"] + "/" + MODEL["filename"], "size": 986047904,
                  "adapter_revision": "none", "tokenizer_revision": MODEL_REVISION,
                  "template_revision": REVISION, "ownership": "SZL_HOLDINGS_OWNED_ARTIFACT"},
        "runtime": {"engine": "llama-cpp-python", "version": "fixture", "library_version": "fixture",
                    "hardware_fingerprint": "sha256:" + "a" * 64, "device": "CPU", "threads": 2},
        "second_brain": {"state": "READY", "retrieval": "public-projection", "node_count": 1,
                         "content_hash": "a" * 16, "content_access": "PUBLIC_PROJECTION_HANDLES_ONLY",
                         "private_graph_present": False, "query_latency": {
                             "label": "MEASURED", "value_ms": 0.01, "unit": "milliseconds",
                             "clock": "time.perf_counter_ns (monotonic)",
                             "basis": "server-observed elapsed duration for this request",
                             "scope": "BrainIndex.ask retrieval, graph expansion, community context, and optional sovereign generation",
                             "excludes": "response serialization, network transport, and browser render time"}},
        "evidence_handles": handles, "evidence_set_sha256": evidence_sha,
        "citations": ["doctrine:F1"], "citations_sha256": sha(["doctrine:F1"]),
        "claims": claims, "claims_sha256": sha(claims),
        "formula_authority": {"locked_proven_count": 8, "locked_proven_ids": LOCKED[:],
                              "applications": applications, "authorization_basis_ids": [],
                              "lambda": dict(LAMBDA)},
        "nemo": nemo, "metrics": {
            "generation_latency": {"label": "MEASURED", "value_ms": 0.01,
                                   "scope": "in-process llama.cpp create_chat_completion call"},
            "prompt_tokens": 12, "completion_tokens": 14, "token_counts_label": "MEASURED"},
        "receipt": {"schema": packet["schema"], "payload": packet, "receipt_sha256": receipt_sha,
                    "signature": {"status": "UNSIGNED_RUNTIME", "durable": False,
                                  "must_be_signed_before_consequential_action": True},
                    "persistence": "EPHEMERAL_PROCESS_MEMORY_ONLY", "prompt_or_evidence_text_persisted": False},
        "anatomy_observation": {"delivery": "DELIVERED", "persistence": "EPHEMERAL_PROCESS_MEMORY_ONLY",
                               "observer_authority": "NONE", "observation_count": 1, "event": event},
        "honesty": {"output_is_owned_khipu_inference": True, "output_is_model_proposal": True,
                    "output_is_signed": False, "action_authority": False,
                    "lambda_is_theorem": False, "private_chain_of_thought_exposed": False},
    }
    if trace_state == "OBSERVED":
        trace = {
            "schema": "szl.trace.receipt-observation/v1", "state": "OBSERVED",
            "operation": "governed_inference_proposal", "authority": "NONE",
            "signature_status": "UNSIGNED_DERIVED_OBSERVATION", "persistence": "RESPONSE_ONLY",
            "delivery": "RESPONSE_SIDECAR_ONLY", "collector_delivery": "UNVERIFIED",
            "trace_context_source": "SERVER_MIDDLEWARE", "trace_id": "1" * 32,
            "span_id": "2" * 16, "trace_flags": "00", "receipt_sha256": receipt_sha,
            "model_sha256": MODEL_HASH, "source_revision": REVISION,
            "diagnostic": {"schema": "szl.trace.diagnostic-minimum/v1", "decision": "PASS",
                           "scope": "STRUCTURAL_DIAGNOSTIC_ONLY", "authority": "NONE",
                           "minimum": 1.0, "threshold": 1.0, "coverage": {"required": 8, "observed": 8},
                           "reason_codes": []},
        }
        trace["observation_sha256"] = sha(trace)
        result["trace_observation"] = trace
    elif trace_state == "UNAVAILABLE":
        result["trace_observation"] = {
            "schema": "szl.trace.receipt-observation/v1", "state": "UNAVAILABLE", "authority": "NONE",
            "delivery": "RESPONSE_SIDECAR_ONLY", "reason_codes": ["OBSERVATION_UNAVAILABLE"],
        }
    return result


def denial():
    return {"schema": "szl.a11oy.owned-khipu-cortex-error/v1", "error": "nemo_text_witness_blocked",
            "state": "UNAVAILABLE", "executed": False, "tool_execution": False,
            "authority_state": "NO_ACTION_AUTHORITY",
            "nemo_witness": {"stage": "TEXT_R1_R5", "decision": "BLOCK", "violated_rules": ["R1"],
                             "rule_version": "doctrine-v11/R1-R5", "input_hash": "sha256:" + "b" * 64}}
