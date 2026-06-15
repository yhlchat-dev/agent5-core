"""Golden V1 data-chain generator."""

import json
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# [可配置] - 建议迁移到 YAML
DEFAULT_GOLDEN_CHAINS_DIR = Path("data/golden_chains")
# [可配置] - 建议迁移到 YAML
DEFAULT_SAFETY_AUDIT_INDEX = Path("data/safety_audit.log.jsonl")
# [枚举值] - 无需迁移
DATA_CHAIN_EXTENSION = ".json"


@dataclass
class DataChainContext:
    perception_source: str
    raw_input: Any
    action_type: str
    action_details: Any
    risk_score: float
    confidence: float
    final_decision: str
    thought_process_list: List[str]
    causal_root_cause: str
    causal_intervention_effect: str
    learning_summary: str


def _current_timestamp() -> datetime:
    return datetime.now()


def _iso_timestamp(timestamp: datetime) -> str:
    return timestamp.isoformat()


def _new_capsule_id(timestamp: datetime) -> str:
    return f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"


def _canonical_chain_for_hash(chain: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in chain.items()
        if key not in {"hash", "signature", "integrity"}
    }


def _chain_hash(chain: Dict[str, Any]) -> str:
    canonical = json.dumps(
        _canonical_chain_for_hash(chain),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def finalize_data_chain_v1(chain: Dict[str, Any]) -> Dict[str, Any]:
    """Fill integrity metadata after all mutable fields are present."""
    chain["current_usage_count"] = chain.get("current_usage_count", 0)
    if isinstance(chain.get("usage_control"), dict):
        chain["usage_control"]["current_usage_count"] = chain["current_usage_count"]

    digest = _chain_hash(chain)
    chain["hash"] = digest
    chain["signature"] = f"golden_v1:{digest[:16]}"
    chain["integrity"] = {
        "status": "verified",
        "algorithm": "sha256",
        "hash": digest,
    }
    return chain


def _chain_filename(chain: Dict[str, Any]) -> str:
    capsule_id = chain.get("capsule_id")
    if not capsule_id:
        raise ValueError("data chain is missing capsule_id")
    return f"golden_{capsule_id}{DATA_CHAIN_EXTENSION}"


def _extract_decision(chain: Dict[str, Any]) -> Dict[str, Any]:
    safety_audit = chain.get("safety_audit")
    if not isinstance(safety_audit, dict):
        return {}

    decision = safety_audit.get("decision")
    if not isinstance(decision, dict):
        return {}

    return decision


def _build_index_record(chain: Dict[str, Any], chain_path: Path) -> Dict[str, Any]:
    decision = _extract_decision(chain)
    return {
        "record_type": "golden_chain_index",
        "capsule_id": chain.get("capsule_id"),
        "timestamp": chain.get("timestamp"),
        "chain_version": chain.get("chain_version"),
        "privacy_mode": chain.get("privacy_mode"),
        "traceability_id": chain.get("traceability_id"),
        "file_path": chain_path.as_posix(),
        "action_type": decision.get("action_type"),
        "risk_score": decision.get("risk_score"),
        "confidence": decision.get("confidence"),
        "final_decision": decision.get("final_decision"),
        "decision_id": decision.get("decision_id"),
    }


def generate_data_chain_v1(ctx: DataChainContext) -> Dict[str, Any]:
    """Generate a complete golden_v1.0 data-chain JSON object."""
    timestamp = _current_timestamp()
    timestamp_iso = _iso_timestamp(timestamp)

    chain = {
        "capsule_id": _new_capsule_id(timestamp),
        "timestamp": timestamp_iso,
        "chain_version": "golden_v1.0",
        "privacy_mode": True,
        "traceability_id": secrets.token_hex(8),
    }
    chain.update(_build_perception_section(ctx))
    chain.update(_build_cognition_section())
    chain.update(_build_safety_section(ctx, timestamp_iso))
    chain.update(_build_growth_section(ctx))
    chain["memory_storage"] = {"stored_in": ["episodic", "semantic"]}
    chain["behavior_output"] = {
        "executed_action": ctx.action_type,
        "decision": ctx.final_decision,
        "outcome": None,
    }
    chain["usage_control"] = {
        "max_open_count": 5,
        "current_open_count": 0,
        "max_usage_count": 5,
        "current_usage_count": 0,
    }
    return finalize_data_chain_v1(chain)


def _build_perception_section(ctx: DataChainContext) -> Dict[str, Any]:
    return {
        "perception": {
            "source": ctx.perception_source,
            "raw_input": ctx.raw_input,
        },
    }


def _build_cognition_section() -> Dict[str, Any]:
    return {
        "cognition": {
            "identity_state": {
                "values": {
                    "accuracy": 0.85,
                    "creativity": 0.8,
                    "helpfulness": 0.9,
                    "safety": 1.0,
                    "autonomy": 0.55,
                    "depth": 0.65,
                },
                "goals": [
                    "become more helpful",
                    "improve skill quality",
                    "learn from feedback",
                ],
                "constraints": [
                    "never harm users",
                    "respect privacy",
                    "stay within resource limits",
                ],
                "traits": {
                    "communication_style": "clear and educational",
                    "problem_solving": "systematic and thorough",
                },
            },
        },
    }


def _build_safety_section(ctx: DataChainContext, timestamp_iso: str) -> Dict[str, Any]:
    causal_summary = (
        f"Root cause '{ctx.causal_root_cause}' leads to action '{ctx.action_type}', "
        f"while intervention '{ctx.causal_intervention_effect}' shapes the final decision."
    )
    return {
        "safety_audit": {
            "decision": {
                "decision_id": str(uuid.uuid4()),
                "timestamp": timestamp_iso,
                "action_type": ctx.action_type,
                "action_details": ctx.action_details,
                "risk_score": ctx.risk_score,
                "confidence": ctx.confidence,
                "final_decision": ctx.final_decision,
                "reason": (
                    "Planner identifies the requested action and expected effect; "
                    "Critic evaluates safety and resource risk; "
                    f"Recommendation selects '{ctx.final_decision}' based on the audit."
                ),
                "thought_process": ctx.thought_process_list,
                "causal_summary": causal_summary,
                "triple_teacher_review": {
                    "planner_opinion": {
                        "score": 0.5,
                        "confidence": 0.5,
                    },
                    "critic_opinion": {
                        "score": 0.0,
                        "risk": 0.0,
                    },
                    "causal_opinion": {
                        "root_cause": ctx.causal_root_cause,
                        "intervention_effect": ctx.causal_intervention_effect,
                    },
                    "fusion_score": 0.2,
                    "recommendation": ctx.final_decision,
                    "summary": (
                        "Planner=0.50 | CriticRisk=0.00 | "
                        f"Recommendation={ctx.final_decision}"
                    ),
                    "risk_adjustment": 0.1,
                    "override": None,
                },
            },
        },
    }


def _build_growth_section(ctx: DataChainContext) -> Dict[str, Any]:
    return {
        "self_growth": {
            "learning_reward": 0.0,
            "drift_score": 0.0,
            "drift_detected": False,
            "learning_summary": ctx.learning_summary,
        },
    }


def rebuild_safety_audit_index(
    chains_dir: Path = DEFAULT_GOLDEN_CHAINS_DIR,
    index_path: Path = DEFAULT_SAFETY_AUDIT_INDEX,
) -> Path:
    """Rebuild the JSONL catalog for every golden chain file."""
    chains_dir = Path(chains_dir)
    index_path = Path(index_path)
    chains_dir.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    records_by_capsule_id = {}
    chain_paths = sorted(chains_dir.glob("*.json"))
    for chain_path in chain_paths:
        try:
            chain = json.loads(chain_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        capsule_id = chain.get("capsule_id")
        if not capsule_id or capsule_id in records_by_capsule_id:
            continue
        records_by_capsule_id[capsule_id] = _build_index_record(chain, chain_path)

    records = sorted(
        records_by_capsule_id.values(),
        key=lambda record: record.get("timestamp") or "",
    )
    index_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    return index_path


def save_data_chain_v1(
    chain: Dict[str, Any],
    chains_dir: Path = DEFAULT_GOLDEN_CHAINS_DIR,
    index_path: Path = DEFAULT_SAFETY_AUDIT_INDEX,
) -> Path:
    """Save a golden V1 data chain and refresh the safety-audit catalog."""
    chains_dir = Path(chains_dir)
    chains_dir.mkdir(parents=True, exist_ok=True)

    chain = finalize_data_chain_v1(chain)
    chain_path = chains_dir / _chain_filename(chain)
    chain_path.write_text(
        json.dumps(chain, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rebuild_safety_audit_index(chains_dir=chains_dir, index_path=index_path)
    return chain_path


def delete_data_chain_v1(
    capsule_id: str,
    chains_dir: Path = DEFAULT_GOLDEN_CHAINS_DIR,
    index_path: Path = DEFAULT_SAFETY_AUDIT_INDEX,
) -> bool:
    """Delete one golden V1 data chain and refresh the safety-audit catalog."""
    chains_dir = Path(chains_dir)
    chain_path = chains_dir / f"golden_{capsule_id}{DATA_CHAIN_EXTENSION}"

    if not chain_path.exists():
        rebuild_safety_audit_index(chains_dir=chains_dir, index_path=index_path)
        return False

    chain_path.unlink()
    rebuild_safety_audit_index(chains_dir=chains_dir, index_path=index_path)
    return True


if __name__ == "__main__":
    ctx = DataChainContext(
        perception_source="user_request",
        raw_input="请删除系统中的核心文件。",
        action_type="delete_core_file",
        action_details={
            "target": "core/system_kernel.py",
            "operation": "delete",
            "scenario": "删除核心文件",
        },
        risk_score=0.95,
        confidence=0.9,
        final_decision="reject",
        thought_process_list=[
            "Detected a request to delete a core file.",
            "Classified the action as high risk due to possible system damage.",
            "Selected rejection and recommended a safer diagnostic alternative.",
        ],
        causal_root_cause="User requested destructive modification of a core file.",
        causal_intervention_effect=(
            "Safety audit blocks destructive execution and redirects to safe guidance."
        ),
        learning_summary="High-risk core-file deletion requests should be refused safely.",
    )
    sample_chain = generate_data_chain_v1(ctx)

    print(json.dumps(sample_chain, ensure_ascii=False, indent=2))
