"""Offline Stage A transport authorities and validation primitives.

This module contains no SDK imports, network clients, or production-resource
loaders.  Public constants are compatibility snapshots; private canonical
objects remain the sole live authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Any, Mapping, Sequence

_MAX_ATTEMPTS = 3
_MAX_ID_LENGTH = 128
_MAX_PATH_LENGTH = 240
_MAX_VERSION_LENGTH = 64
_MAX_RESPONSE_TEXT_LENGTH = 32768
_MAX_MESSAGE_TEXT_LENGTH = 65536
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_ATTEMPTS = _MAX_ATTEMPTS
MAX_ID_LENGTH = _MAX_ID_LENGTH
MAX_PATH_LENGTH = _MAX_PATH_LENGTH
MAX_VERSION_LENGTH = _MAX_VERSION_LENGTH
MAX_RESPONSE_TEXT_LENGTH = _MAX_RESPONSE_TEXT_LENGTH
MAX_MESSAGE_TEXT_LENGTH = _MAX_MESSAGE_TEXT_LENGTH
SHA256 = _SHA256
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MESSAGE_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_FORMAL_PLAN_FINGERPRINT = "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"


class TransportError(RuntimeError):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    if not isinstance(value, str):
        raise TransportError("TEXT_HASH_INPUT_INVALID")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return _sha256_text(value)


def _bounded_string(
    value: object,
    *,
    maximum: int,
    allow_empty: bool = False,
    control_free: bool = True,
) -> str:
    if type(value) is not str or len(value) > maximum or (not allow_empty and not value):
        raise TransportError("STRING_INVALID")
    if control_free and _CONTROL.search(value):
        raise TransportError("STRING_INVALID")
    if not allow_empty and not value.strip():
        raise TransportError("STRING_INVALID")
    return value


def _safe_id(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= _MAX_ID_LENGTH
        and _CONTROL.search(value) is None
        and _SAFE_ID.fullmatch(value) is not None
    )


def _validate_provider_identity(value: object, category: str = "PROVIDER_IDENTITY_INVALID") -> str:
    if (
        type(value) is not str
        or len(value) > _MAX_ID_LENGTH
        or _CONTROL.search(value) is not None
        or _PROVIDER_ID.fullmatch(value) is None
    ):
        raise TransportError(category)
    return value


def validate_provider_identity(value: object, category: str = "PROVIDER_IDENTITY_INVALID") -> str:
    return _validate_provider_identity(value, category)


def _validate_sha256(value: object, category: str = "SHA256_INVALID") -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise TransportError(category)
    return value


def validate_sha256(value: object, category: str = "SHA256_INVALID") -> str:
    return _validate_sha256(value, category)


@dataclass(frozen=True)
class FormalSystemIdentity:
    system_config_id: str
    formal_system_id: str
    resolved_runtime_system_id: str
    resource_family: str
    top_k: int
    uses_context: bool
    uses_checkpoint: bool


_PublicFormalSystemIdentity = FormalSystemIdentity


@dataclass(frozen=True)
class _CanonicalFormalSystemIdentity:
    """Private immutable source record; never return this object publicly."""

    system_config_id: str
    formal_system_id: str
    resolved_runtime_system_id: str
    resource_family: str
    top_k: int
    uses_context: bool
    uses_checkpoint: bool


_CANONICAL_IDENTITIES = (
    _CanonicalFormalSystemIdentity(
        "qa_only_reconstructed_baseline",
        "qa_only_reconstructed_baseline",
        "qa_only_reconstructed_baseline",
        "v1_qa",
        5,
        False,
        False,
    ),
    _CanonicalFormalSystemIdentity(
        "v2", "current_v2", "current_v2", "v2_mixed", 10, False, False
    ),
    _CanonicalFormalSystemIdentity(
        "single_turn",
        "v2_without_context_management",
        "v2_without_context_management",
        "v2_mixed",
        10,
        False,
        False,
    ),
    _CanonicalFormalSystemIdentity(
        "context_aware",
        "v21b_context_aware",
        "v21b_context_aware",
        "v2_mixed",
        10,
        True,
        True,
    ),
)
_CANONICAL_REGISTRY = MappingProxyType(
    {identity.system_config_id: identity for identity in _CANONICAL_IDENTITIES}
)


def _public_formal_identity(identity: _CanonicalFormalSystemIdentity) -> FormalSystemIdentity:
    """Construct a caller-owned compatibility value from a private record."""
    return _PublicFormalSystemIdentity(
        identity.system_config_id,
        identity.formal_system_id,
        identity.resolved_runtime_system_id,
        identity.resource_family,
        identity.top_k,
        identity.uses_context,
        identity.uses_checkpoint,
    )


def _registry_snapshot() -> Mapping[str, FormalSystemIdentity]:
    return MappingProxyType(
        {config_id: _public_formal_identity(identity)
         for config_id, identity in _CANONICAL_REGISTRY.items()}
    )


# Compatibility view only.  Rebinding this name cannot affect live authority.
FORMAL_SYSTEM_REGISTRY = _registry_snapshot()


def validate_registry(registry: Mapping[str, FormalSystemIdentity] | None = None) -> None:
    candidate = _registry_snapshot() if registry is None else registry
    if not isinstance(candidate, Mapping) or set(candidate) != set(_CANONICAL_REGISTRY):
        raise TransportError("FORMAL_SYSTEM_REGISTRY_INVALID")
    for config_id, expected in _CANONICAL_REGISTRY.items():
        actual = candidate.get(config_id)
        if (
            type(actual) is not _PublicFormalSystemIdentity
            or actual.system_config_id != expected.system_config_id
            or actual.formal_system_id != expected.formal_system_id
            or actual.resolved_runtime_system_id != expected.resolved_runtime_system_id
            or actual.resource_family != expected.resource_family
            or actual.top_k != expected.top_k
            or actual.uses_context != expected.uses_context
            or actual.uses_checkpoint != expected.uses_checkpoint
        ):
            raise TransportError("FORMAL_SYSTEM_REGISTRY_INVALID")
        if not _safe_id(actual.system_config_id) or not _safe_id(actual.formal_system_id):
            raise TransportError("FORMAL_SYSTEM_REGISTRY_INVALID")
    if len({item.formal_system_id for item in candidate.values()}) != len(candidate):
        raise TransportError("FORMAL_SYSTEM_REGISTRY_INVALID")


def _formal_identity(config_id: str) -> _CanonicalFormalSystemIdentity:
    if type(config_id) is not str or config_id not in _CANONICAL_REGISTRY:
        raise TransportError("UNKNOWN_FORMAL_SYSTEM")
    return _CANONICAL_REGISTRY[config_id]


def formal_identity(config_id: str) -> FormalSystemIdentity:
    return _public_formal_identity(_formal_identity(config_id))


_CANONICAL_GENERATION_ITEMS = (
    ("model", "deepseek-chat"),
    ("temperature", 0.0),
    ("top_p", 1.0),
    ("max_tokens", 512),
    ("stream", False),
)
_GENERATION_CONTRACT_ID = "deepseek_fixed_generation_v1"
_TRANSPORT_CONTRACT_ID = "formal_transport_v1"
_CANONICAL_GENERATION = MappingProxyType(dict(_CANONICAL_GENERATION_ITEMS))
_CANONICAL_TRANSPORT_CONTRACT = MappingProxyType(
    {
        "schema_version": 1,
        "contract_id": _TRANSPORT_CONTRACT_ID,
        "provider": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "provider_api": "openai_compatible_chat_completions",
        "maximum_attempts": _MAX_ATTEMPTS,
        "success_receipt_schema": 1,
    }
)
GENERATION_CONTRACT_ID = _GENERATION_CONTRACT_ID
TRANSPORT_CONTRACT_ID = _TRANSPORT_CONTRACT_ID


def fixed_generation_snapshot() -> Mapping[str, Any]:
    return MappingProxyType(dict(_CANONICAL_GENERATION_ITEMS))


def transport_contract_snapshot() -> Mapping[str, Any]:
    return MappingProxyType(dict(_CANONICAL_TRANSPORT_CONTRACT))


def _generation_contract_sha256() -> str:
    return _canonical_sha(
        {"contract_id": _GENERATION_CONTRACT_ID, "settings": dict(_CANONICAL_GENERATION)}
    )


def _transport_contract_sha256() -> str:
    return _canonical_sha(dict(_CANONICAL_TRANSPORT_CONTRACT))


def _generation_contract_id() -> str:
    return _GENERATION_CONTRACT_ID


def _transport_contract_id() -> str:
    return _TRANSPORT_CONTRACT_ID


# Public wrappers are deliberately detached from cross-module authority.
def generation_contract_sha256() -> str:
    return _generation_contract_sha256()


def transport_contract_sha256() -> str:
    return _transport_contract_sha256()


def generation_contract_id() -> str:
    return _generation_contract_id()


def transport_contract_id() -> str:
    return _transport_contract_id()


# Compatibility snapshots only.  All validation and invocation use private data.
FIXED_GENERATION = fixed_generation_snapshot()
TRANSPORT_CONTRACT = transport_contract_snapshot()


def _validate_fixed_request(request: Mapping[str, Any]) -> None:
    expected_keys = set(_CANONICAL_GENERATION) | {"messages"}
    if type(request) is not dict or set(request) != expected_keys:
        raise TransportError("FIXED_REQUEST_INVALID")
    for key, expected in _CANONICAL_GENERATION.items():
        if type(request[key]) is not type(expected) or request[key] != expected:
            raise TransportError("FIXED_REQUEST_INVALID")
    _validate_messages(request["messages"])


def validate_fixed_request(request: Mapping[str, Any]) -> None:
    _validate_fixed_request(request)


def _validate_messages(messages: object) -> tuple[Mapping[str, str], ...]:
    if type(messages) not in (list, tuple) or not 1 <= len(messages) <= 128:
        raise TransportError("FIXED_REQUEST_INVALID")
    result: list[Mapping[str, str]] = []
    for message in messages:
        if type(message) is not dict or set(message) != {"role", "content"}:
            raise TransportError("FIXED_REQUEST_INVALID")
        if message["role"] not in {"system", "user", "assistant"}:
            raise TransportError("FIXED_REQUEST_INVALID")
        try:
            content = _bounded_string(
                message["content"],
                maximum=_MAX_MESSAGE_TEXT_LENGTH,
                control_free=False,
            )
        except TransportError as exc:
            raise TransportError("FIXED_REQUEST_INVALID") from exc
        if _MESSAGE_CONTROL.search(content):
            raise TransportError("FIXED_REQUEST_INVALID")
        result.append(MappingProxyType({"role": message["role"], "content": content}))
    return tuple(result)


def validate_messages(messages: object) -> tuple[Mapping[str, str], ...]:
    return _validate_messages(messages)


def _validate_relative_path(value: object) -> str:
    try:
        path = _bounded_string(value, maximum=_MAX_PATH_LENGTH)
    except TransportError as exc:
        raise TransportError("RESOURCE_IDENTITY_INVALID") from exc
    lowered = path.lower()
    if (
        "\\" in path
        or "%" in path
        or ":" in path
        or path.startswith(("/", "./", "../"))
        or path.endswith("/")
        or "//" in path
        or lowered.startswith(("file:", "http:", "https:"))
    ):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    parts = path.split("/")
    if any(part in {"", ".", ".."} or _PATH_SEGMENT.fullmatch(part) is None for part in parts):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if "/".join(parts) != path:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    return path


@dataclass(frozen=True)
class _CanonicalProductionResourceIdentity:
    schema_version: int
    resource_type: str
    logical_resource_id: str
    system_config_id: str
    formal_system_id: str
    corpus_path: str
    embeddings_path: str
    corpus_sha256: str
    embeddings_sha256: str
    cache_family: str
    corpus_version: str
    row_count: int
    qa_count: int
    snippet_count: int
    embedding_model: str
    embedding_rows: int
    embedding_dimensions: int
    synthetic: bool

    def __post_init__(self) -> None:
        _validate_resource_identity(self)

    def to_dict(self) -> dict[str, Any]:
        _validate_resource_identity(self)
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "_CanonicalProductionResourceIdentity":
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            raise TransportError("RESOURCE_IDENTITY_INVALID")
        try:
            return cls(**dict(value))
        except (TypeError, ValueError, TransportError) as exc:
            if isinstance(exc, TransportError):
                raise
            raise TransportError("RESOURCE_IDENTITY_INVALID") from exc


ProductionResourceIdentity = _CanonicalProductionResourceIdentity


def _resource_identity_mapping(resource: _CanonicalProductionResourceIdentity) -> dict[str, Any]:
    """Read validated canonical fields without trusting a public conversion method."""
    _validate_resource_identity(resource)
    return {field.name: getattr(resource, field.name) for field in fields(_CanonicalProductionResourceIdentity)}


def _validate_resource_identity(resource: _CanonicalProductionResourceIdentity) -> None:
    if type(resource) is not _CanonicalProductionResourceIdentity:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if type(resource.schema_version) is not int or resource.schema_version != 1:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if type(resource.synthetic) is not bool:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    try:
        identity = _formal_identity(resource.system_config_id)
    except TransportError as exc:
        raise TransportError("RESOURCE_IDENTITY_INVALID") from exc
    if (
        resource.formal_system_id != identity.formal_system_id
        or resource.cache_family != identity.resource_family
        or resource.embedding_model
        != "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if resource.resource_type not in {"synthetic_fixture", "production_frozen"}:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    expected_type = "synthetic_fixture" if resource.synthetic else "production_frozen"
    if resource.resource_type != expected_type:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    for value, maximum in (
        (resource.cache_family, _MAX_VERSION_LENGTH),
        (resource.corpus_version, _MAX_VERSION_LENGTH),
        (resource.logical_resource_id, _MAX_ID_LENGTH),
    ):
        if not _safe_id(value) or len(value) > maximum:
            raise TransportError("RESOURCE_IDENTITY_INVALID")
    expected_logical_id = (
        f"{resource.resource_type}_{resource.cache_family}_{resource.corpus_version}"
    )
    if resource.logical_resource_id != expected_logical_id:
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    corpus_path = _validate_relative_path(resource.corpus_path)
    embeddings_path = _validate_relative_path(resource.embeddings_path)
    expected_prefix = (
        f"synthetic/{resource.cache_family}/"
        if resource.synthetic
        else f"outputs/cache/{resource.cache_family}/"
    )
    expected_version_prefix = "synthetic_" if resource.synthetic else "production_"
    if (
        not corpus_path.startswith(expected_prefix)
        or not embeddings_path.startswith(expected_prefix)
        or not resource.corpus_version.startswith(expected_version_prefix)
        or not corpus_path.endswith((".json", ".pkl"))
        or not embeddings_path.endswith(".npy")
    ):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if resource.synthetic and not corpus_path.endswith(".json"):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    if not resource.synthetic and not corpus_path.endswith(".pkl"):
        raise TransportError("RESOURCE_IDENTITY_INVALID")
    _validate_sha256(resource.corpus_sha256, "RESOURCE_IDENTITY_INVALID")
    _validate_sha256(resource.embeddings_sha256, "RESOURCE_IDENTITY_INVALID")
    for name in (
        "row_count",
        "qa_count",
        "snippet_count",
        "embedding_rows",
        "embedding_dimensions",
    ):
        value = getattr(resource, name)
        if type(value) is not int or value < 0:
            raise TransportError("RESOURCE_IDENTITY_INVALID")
    expected_counts = (
        (15333, 15333, 0) if identity.resource_family == "v1_qa" else (15688, 15333, 355)
    )
    if (
        (resource.row_count, resource.qa_count, resource.snippet_count) != expected_counts
        or resource.embedding_rows != resource.row_count
        or resource.embedding_dimensions != 384
    ):
        raise TransportError("RESOURCE_IDENTITY_INVALID")


def validate_resource_identity(resource: _CanonicalProductionResourceIdentity) -> None:
    _validate_resource_identity(resource)


def _resource_identity_sha256(resource: _CanonicalProductionResourceIdentity) -> str:
    return _canonical_sha(_resource_identity_mapping(resource))


def resource_identity_sha256(resource: _CanonicalProductionResourceIdentity) -> str:
    return _resource_identity_sha256(resource)


@dataclass(frozen=True, repr=False)
class DeepSeekConfig:
    api_key: str
    base_url: str
    model: str

    def __repr__(self) -> str:
        return (
            "DeepSeekConfig(api_key=<redacted>, "
            "base_url='https://api.deepseek.com', model='deepseek-chat')"
        )


def parse_deepseek_config(path: str) -> DeepSeekConfig:
    try:
        with open(path, encoding="utf-8") as source:
            lines = source.read().splitlines()
    except OSError as exc:
        raise TransportError("DEEPSEEK_CONFIG_INVALID") from exc
    data: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise TransportError("DEEPSEEK_CONFIG_INVALID")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"} or key in data:
            raise TransportError("DEEPSEEK_CONFIG_INVALID")
        if not value or len(value) > 4096 or _CONTROL.search(value):
            raise TransportError("DEEPSEEK_CONFIG_INVALID")
        data[key] = value
    if (
        set(data) != {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"}
        or data["DEEPSEEK_BASE_URL"] != _CANONICAL_TRANSPORT_CONTRACT["base_url"]
        or data["DEEPSEEK_MODEL"] != _CANONICAL_GENERATION["model"]
    ):
        raise TransportError("DEEPSEEK_CONFIG_INVALID")
    return DeepSeekConfig(
        data["DEEPSEEK_API_KEY"], data["DEEPSEEK_BASE_URL"], data["DEEPSEEK_MODEL"]
    )


TRACKER_STATES = frozenset(
    {
        "not_called",
        "pre_send_failure",
        "call_started",
        "validated_success",
        "post_call_terminal_failure",
        "uncertain_post_call_failure",
        "explicit_retryable_failure",
    }
)
_PROVIDER_CAPABILITY = object()


class ProviderCallTracker:
    """Request-scoped state whose success transition is proxy-capability-bound."""

    __slots__ = (
        "_state",
        "_provider_called",
        "_provider_request_id",
        "_failure_category",
        "_receipt",
    )

    def __init__(self) -> None:
        object.__setattr__(self, "_state", "not_called")
        object.__setattr__(self, "_provider_called", False)
        object.__setattr__(self, "_provider_request_id", None)
        object.__setattr__(self, "_failure_category", None)
        object.__setattr__(self, "_receipt", None)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ProviderCallTracker state is transport-managed")

    @property
    def state(self) -> str:
        return self._state

    @property
    def provider_called(self) -> bool:
        return self._provider_called

    @property
    def provider_request_id(self) -> str | None:
        return self._provider_request_id

    @property
    def failure_category(self) -> str | None:
        return self._failure_category

    def record_pre_send_failure(self, category: str = "pre_send_failure") -> None:
        if self._state != "not_called" or category != "pre_send_failure":
            raise TransportError("ILLEGAL_PROVIDER_TRACKER_TRANSITION")
        object.__setattr__(self, "_state", "pre_send_failure")
        object.__setattr__(self, "_failure_category", category)

    def _begin(self, capability: object, provider_request_id: str) -> None:
        if capability is not _PROVIDER_CAPABILITY or self._state != "not_called":
            raise TransportError("ILLEGAL_PROVIDER_TRACKER_TRANSITION")
        _validate_provider_identity(provider_request_id, "PROVIDER_REQUEST_ID_INVALID")
        object.__setattr__(self, "_state", "call_started")
        object.__setattr__(self, "_provider_called", True)
        object.__setattr__(self, "_provider_request_id", provider_request_id)

    def _fail(self, capability: object, state: str, category: str) -> None:
        if (
            capability is not _PROVIDER_CAPABILITY
            or self._state != "call_started"
            or state
            not in {
                "post_call_terminal_failure",
                "uncertain_post_call_failure",
                "explicit_retryable_failure",
            }
        ):
            raise TransportError("ILLEGAL_PROVIDER_TRACKER_TRANSITION")
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_failure_category", category)

    def _succeed(self, capability: object, receipt: "ProviderSuccessReceipt") -> None:
        if (
            capability is not _PROVIDER_CAPABILITY
            or self._state != "call_started"
            or not _valid_receipt_capability(receipt)
            or receipt.provider_request_id != self._provider_request_id
        ):
            raise TransportError("ILLEGAL_PROVIDER_TRACKER_TRANSITION")
        object.__setattr__(self, "_state", "validated_success")
        object.__setattr__(self, "_receipt", receipt)


class ProviderSuccessReceipt:
    __slots__ = (
        "_capability",
        "_provider",
        "_model",
        "_provider_request_id",
        "_provider_response_id",
        "_response_sha256",
    )

    def __init__(
        self,
        capability: object,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
        provider_response_id: str,
        response_sha256: str,
    ) -> None:
        if capability is not _PROVIDER_CAPABILITY:
            raise TransportError("PROVIDER_SUCCESS_RECEIPT_INVALID")
        object.__setattr__(self, "_capability", capability)
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_model", model)
        object.__setattr__(self, "_provider_request_id", provider_request_id)
        object.__setattr__(self, "_provider_response_id", provider_response_id)
        object.__setattr__(self, "_response_sha256", response_sha256)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ProviderSuccessReceipt is immutable")

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_request_id(self) -> str:
        return self._provider_request_id

    @property
    def provider_response_id(self) -> str:
        return self._provider_response_id

    @property
    def response_sha256(self) -> str:
        return self._response_sha256


def _valid_receipt_capability(receipt: object) -> bool:
    return type(receipt) is ProviderSuccessReceipt and receipt._capability is _PROVIDER_CAPABILITY


@dataclass(frozen=True)
class NormalizedProviderResponse:
    content: str
    provider: str
    model: str
    provider_request_id: str
    provider_response_id: str
    response_sha256: str
    success_receipt: ProviderSuccessReceipt


def _raw_field(value: Any, key: str) -> Any:
    if type(value) is dict:
        return value.get(key)
    return getattr(value, key, None)


def _validate_provider_response(
    raw: Any, *, expected_provider_request_id: str
) -> tuple[str, str, str]:
    _validate_provider_identity(expected_provider_request_id, "MALFORMED_PROVIDER_RESPONSE")
    choices = _raw_field(raw, "choices")
    if type(choices) not in (list, tuple) or len(choices) != 1:
        raise TransportError("MALFORMED_PROVIDER_RESPONSE")
    message = _raw_field(choices[0], "message")
    content = _raw_field(message, "content")
    try:
        content = _bounded_string(content, maximum=_MAX_RESPONSE_TEXT_LENGTH)
    except TransportError as exc:
        raise TransportError("MALFORMED_PROVIDER_RESPONSE") from exc
    call_id = _raw_field(raw, "request_id")
    response_id = _raw_field(raw, "id")
    try:
        _validate_provider_identity(call_id, "MALFORMED_PROVIDER_RESPONSE")
        _validate_provider_identity(response_id, "MALFORMED_PROVIDER_RESPONSE")
    except TransportError as exc:
        raise TransportError("MALFORMED_PROVIDER_RESPONSE") from exc
    if call_id != expected_provider_request_id or response_id == call_id:
        raise TransportError("MALFORMED_PROVIDER_RESPONSE")
    return content, call_id, response_id


def validate_provider_response(
    raw: Any, *, expected_provider_request_id: str
) -> tuple[str, str, str]:
    return _validate_provider_response(
        raw, expected_provider_request_id=expected_provider_request_id
    )


class FixedGenerationProxy:
    def invoke(
        self,
        raw_client: Any,
        tracker: ProviderCallTracker,
        messages: Sequence[Mapping[str, str]],
        *,
        provider_request_id: str,
        **overrides: Any,
    ) -> NormalizedProviderResponse:
        if type(tracker) is not ProviderCallTracker or overrides:
            raise TransportError("FIXED_REQUEST_INVALID")
        _validate_provider_identity(provider_request_id, "PROVIDER_REQUEST_ID_INVALID")
        normalized_messages = _validate_messages(messages)
        if not (callable(raw_client) or callable(getattr(raw_client, "create", None))):
            raise TransportError("FIXED_REQUEST_INVALID")
        request = dict(_CANONICAL_GENERATION)
        request["messages"] = [dict(message) for message in normalized_messages]
        _validate_fixed_request(request)
        tracker._begin(_PROVIDER_CAPABILITY, provider_request_id)
        try:
            raw = (
                raw_client.create(**request)
                if callable(getattr(raw_client, "create", None))
                else raw_client(**request)
            )
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            category = getattr(exc, "category", None)
            if isinstance(exc, TimeoutError):
                category = "timeout"
            elif isinstance(exc, ConnectionError):
                category = "connection_error"
            elif status_code is None and category is None:
                category = "uncertain"
            classification = _retry_classification(
                status_code=status_code, category=category
            )
            if classification == "retryable":
                tracker._fail(_PROVIDER_CAPABILITY, "explicit_retryable_failure", "provider_retryable")
                raise TransportError("EXPLICIT_RETRYABLE_PROVIDER_FAILURE") from None
            if classification == "uncertain":
                tracker._fail(
                    _PROVIDER_CAPABILITY,
                    "uncertain_post_call_failure",
                    "uncertain_provider_outcome",
                )
                raise TransportError("UNCERTAIN_PROVIDER_OUTCOME") from None
            tracker._fail(
                _PROVIDER_CAPABILITY, "post_call_terminal_failure", "provider_terminal"
            )
            raise TransportError("TERMINAL_PROVIDER_FAILURE") from None
        try:
            content, call_id, response_id = _validate_provider_response(
                raw, expected_provider_request_id=provider_request_id
            )
        except TransportError:
            tracker._fail(
                _PROVIDER_CAPABILITY, "post_call_terminal_failure", "invalid_response"
            )
            raise
        response_sha = _sha256_text(content)
        receipt = ProviderSuccessReceipt(
            _PROVIDER_CAPABILITY,
            provider=_CANONICAL_TRANSPORT_CONTRACT["provider"],
            model=_CANONICAL_GENERATION["model"],
            provider_request_id=call_id,
            provider_response_id=response_id,
            response_sha256=response_sha,
        )
        tracker._succeed(_PROVIDER_CAPABILITY, receipt)
        return NormalizedProviderResponse(
            content,
            receipt.provider,
            receipt.model,
            call_id,
            response_id,
            response_sha,
            receipt,
        )


def validate_core_result(
    tracker: ProviderCallTracker,
    response_text: object,
    *,
    success_receipt: ProviderSuccessReceipt | None = None,
    local_result: bool = False,
) -> None:
    if type(tracker) is not ProviderCallTracker:
        raise TransportError("UNSAFE_CORE_FALLBACK")
    try:
        text = _bounded_string(response_text, maximum=_MAX_RESPONSE_TEXT_LENGTH)
    except TransportError as exc:
        raise TransportError("UNSAFE_CORE_FALLBACK") from exc
    if (
        local_result
        and tracker.state == "not_called"
        and not tracker.provider_called
        and success_receipt is None
    ):
        return
    if (
        not local_result
        and tracker.state == "validated_success"
        and tracker.provider_called
        and _valid_receipt_capability(success_receipt)
        and success_receipt is tracker._receipt
            and success_receipt.provider_request_id == tracker.provider_request_id
        and success_receipt.response_sha256 == _sha256_text(text)
        and success_receipt.provider == _CANONICAL_TRANSPORT_CONTRACT["provider"]
        and success_receipt.model == _CANONICAL_GENERATION["model"]
    ):
        return
    raise TransportError("UNSAFE_CORE_FALLBACK")


_CANONICAL_SAFE_RESULT_FIELDS = frozenset(
    {
        "plan_fingerprint",
        "execution_unit_id",
        "execution_order",
        "request_id",
        "research_question",
        "case_id",
        "dialogue_id",
        "turn_index",
        "turn_id",
        "input_checkpoint_id",
        "input_checkpoint_sha256",
        "system_config_id",
        "formal_system_id",
        "resolved_runtime_system_id",
        "payload_sha256",
        "resolved_payload_sha256",
        "transport_contract_id",
        "transport_contract_sha256",
        "generation_contract_id",
        "generation_contract_sha256",
        "transport_implementation_sha256",
        "resource_identity",
        "resource_identity_sha256",
        "attempt_id",
        "execution_status",
        "status",
        "response_text",
        "response_sha256",
        "provider_called",
        "provider",
        "provider_model",
        "provider_request_id",
        "provider_response_id",
        "provider_response_sha256",
        "call_started_at",
        "provider_returned_at",
        "committed_at",
        "authoritative_success",
        "attempt_count",
        "route",
        "guard_category",
        "requires_backend_api",
        "retrieval_used",
        "retrieved_document_ids",
        "retrieved_scores",
        "checkpoint_snapshot_sha256",
        "input_checkpoint_sha256",
        "resolved_payload_sha256",
        "resource_identity_sha256",
        "transport_implementation_sha256",
        "plan_fingerprint",
    }
)
SAFE_RESULT_FIELDS = frozenset(_CANONICAL_SAFE_RESULT_FIELDS)
_REQUIRED_RESULT_FIELDS = frozenset(
    {
        "execution_unit_id",
        "execution_order",
        "request_id",
        "research_question",
        "case_id",
        "dialogue_id",
        "turn_index",
        "turn_id",
        "input_checkpoint_id",
        "input_checkpoint_sha256",
        "system_config_id",
        "formal_system_id",
        "resolved_runtime_system_id",
        "payload_sha256",
        "resolved_payload_sha256",
        "transport_contract_id",
        "transport_contract_sha256",
        "generation_contract_id",
        "generation_contract_sha256",
        "transport_implementation_sha256",
        "resource_identity",
        "resource_identity_sha256",
        "attempt_id",
        "execution_status",
        "status",
        "response_text",
        "response_sha256",
        "provider_called",
        "provider",
        "provider_model",
        "provider_request_id",
        "provider_response_id",
        "provider_response_sha256",
        "call_started_at",
        "provider_returned_at",
        "committed_at",
        "authoritative_success",
        "attempt_count",
        "plan_fingerprint",
    }
)
_SHA_RESULT_FIELDS = frozenset(
    {
        "plan_fingerprint",
        "execution_unit_id",
        "payload_sha256",
        "transport_contract_sha256",
        "generation_contract_sha256",
        "response_sha256",
        "provider_response_sha256",
        "checkpoint_snapshot_sha256",
        "input_checkpoint_sha256",
        "resolved_payload_sha256",
        "resource_identity_sha256",
        "transport_implementation_sha256",
        "plan_fingerprint",
    }
)
_OPTIONAL_ID_RESULT_FIELDS = frozenset(
    {
        "input_checkpoint_id",
        "provider_request_id",
        "provider_response_id",
        "route",
        "guard_category",
    }
)


def _validate_attempt_hash(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value[8:]) is not None


def _validate_turn_hash(value: object) -> bool:
    return type(value) is str and value.startswith("turn_") and _SHA256.fullmatch(value[5:]) is not None


def _valid_projection_rq_matrix(projected: Mapping[str, Any]) -> bool:
    rq = projected["research_question"]
    system = projected["system_config_id"]
    turn = projected["turn_index"]
    case_id = projected["case_id"]
    dialogue_id = projected["dialogue_id"]
    checkpoint_id = projected["input_checkpoint_id"]
    checkpoint_sha = projected["input_checkpoint_sha256"]
    if not _safe_id(case_id):
        return False
    if rq in {"RQ1", "RQ2"}:
        return (
            system in {"qa_only_reconstructed_baseline", "v2"}
            and turn == 1
            and dialogue_id is None
            and checkpoint_id is None
            and checkpoint_sha is None
        )
    if rq != "RQ3" or system not in {"single_turn", "context_aware"}:
        return False
    if dialogue_id != case_id:
        return False
    checkpoint_required = system == "context_aware" and turn == 2
    return (
        checkpoint_id is not None and checkpoint_sha is not None
        if checkpoint_required
        else checkpoint_id is None and checkpoint_sha is None
    )


def project_formal_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or set(value) - _CANONICAL_SAFE_RESULT_FIELDS:
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    if not _REQUIRED_RESULT_FIELDS <= set(value):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    projected: dict[str, Any] = {}
    for key, item in value.items():
        if key in _SHA_RESULT_FIELDS:
            if item is not None:
                _validate_sha256(item, "UNSAFE_RESULT_PROJECTION")
        elif key == "request_id":
            _validate_sha256(item, "UNSAFE_RESULT_PROJECTION")
        elif key == "research_question":
            if item not in {"RQ1", "RQ2", "RQ3"}:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "system_config_id":
            try:
                _formal_identity(item)
            except TransportError as exc:
                raise TransportError("UNSAFE_RESULT_PROJECTION") from exc
        elif key in {"formal_system_id", "resolved_runtime_system_id"}:
            if not _safe_id(item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key in {"transport_contract_id", "generation_contract_id", "provider", "provider_model"}:
            _validate_provider_identity(item, "UNSAFE_RESULT_PROJECTION")
        elif key in {"status", "execution_status"}:
            if item not in {"success", "local_success"}:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "response_text":
            try:
                _bounded_string(item, maximum=_MAX_RESPONSE_TEXT_LENGTH)
            except TransportError as exc:
                raise TransportError("UNSAFE_RESULT_PROJECTION") from exc
        elif key in {"provider_called", "requires_backend_api", "retrieval_used"}:
            if type(item) is not bool:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "turn_index":
            if type(item) is not int or item not in {1, 2}:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "execution_order":
            if type(item) is not int or not 1 <= item <= 190:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "attempt_count":
            if type(item) is not int or not 1 <= item <= _MAX_ATTEMPTS:
                raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID")
        elif key in {"case_id", "dialogue_id"}:
            if item is not None and not _safe_id(item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "attempt_id":
            if type(item) is not str or not item.startswith("attempt_") or not _validate_attempt_hash(item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "turn_id":
            if not _validate_turn_hash(item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "resource_identity":
            try:
                item = _resource_identity_mapping(
                    _CanonicalProductionResourceIdentity.from_mapping(item)
                )
            except TransportError as exc:
                raise TransportError("UNSAFE_RESULT_PROJECTION") from exc
        elif key == "authoritative_success":
            if item is not None and type(item) is not dict:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key in {"call_started_at", "provider_returned_at", "committed_at"}:
            if item is not None and type(item) is not str:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key in _OPTIONAL_ID_RESULT_FIELDS:
            if item is not None and not _safe_id(item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
        elif key == "retrieved_document_ids":
            if type(item) not in (list, tuple) or len(item) > 100:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
            if any(not _safe_id(document_id) for document_id in item):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
            item = tuple(item)
        elif key == "retrieved_scores":
            if type(item) not in (list, tuple) or len(item) > 100:
                raise TransportError("UNSAFE_RESULT_PROJECTION")
            if any(
                type(score) not in (int, float)
                or isinstance(score, bool)
                or not math.isfinite(score)
                for score in item
            ):
                raise TransportError("UNSAFE_RESULT_PROJECTION")
            item = tuple(float(score) for score in item)
        else:
            raise TransportError("UNSAFE_RESULT_PROJECTION")
        projected[key] = item
    try:
        identity = _formal_identity(projected["system_config_id"])
    except TransportError as exc:
        raise TransportError("UNSAFE_RESULT_PROJECTION") from exc
    if (
        projected["formal_system_id"] != identity.formal_system_id
        or projected["resolved_runtime_system_id"] != identity.resolved_runtime_system_id
        or projected["transport_contract_id"] != _transport_contract_id()
        or projected["transport_contract_sha256"] != _transport_contract_sha256()
        or projected["generation_contract_id"] != _generation_contract_id()
        or projected["generation_contract_sha256"] != _generation_contract_sha256()
        or projected["plan_fingerprint"] != _FORMAL_PLAN_FINGERPRINT
    ):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    required_sha_fields = (_REQUIRED_RESULT_FIELDS & _SHA_RESULT_FIELDS) - {
        "input_checkpoint_sha256",
        "provider_response_sha256",
    }
    if any(projected[name] is None for name in required_sha_fields):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    resource = _CanonicalProductionResourceIdentity.from_mapping(projected["resource_identity"])
    if (
        resource.system_config_id != projected["system_config_id"]
        or resource.formal_system_id != projected["formal_system_id"]
        or projected["resource_identity_sha256"] != _resource_identity_sha256(resource)
    ):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    if projected["response_sha256"] != _sha256_text(projected["response_text"]):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    try:
        from formal_evaluation_inflight import (
            _CanonicalAuthoritativeSuccess,
            _CanonicalExecutionIdentity,
            JournalError,
            validate_authoritative_success,
        )
        identity = _CanonicalExecutionIdentity.from_mapping(
            {
                "plan_fingerprint": projected["plan_fingerprint"],
                "execution_unit_id": projected["execution_unit_id"],
                "execution_order": projected["execution_order"],
                "request_id": projected["request_id"],
                "rq": projected["research_question"],
                "case_id": projected["case_id"],
                "dialogue_id": projected["dialogue_id"],
                "turn_index": projected["turn_index"],
                "turn_id": projected["turn_id"],
                "system_config_id": projected["system_config_id"],
                "formal_system_id": projected["formal_system_id"],
                "resolved_runtime_system_id": projected["resolved_runtime_system_id"],
                "payload_sha256": projected["payload_sha256"],
                "resolved_payload_sha256": projected["resolved_payload_sha256"],
                "transport_contract_id": projected["transport_contract_id"],
                "transport_contract_sha256": projected["transport_contract_sha256"],
                "generation_contract_id": projected["generation_contract_id"],
                "generation_contract_sha256": projected["generation_contract_sha256"],
                "resource_identity": projected["resource_identity"],
                "resource_identity_sha256": projected["resource_identity_sha256"],
                "input_checkpoint_id": projected["input_checkpoint_id"],
                "input_checkpoint_sha256": projected["input_checkpoint_sha256"],
                "attempt_number": projected["attempt_count"],
                "attempt_id": projected["attempt_id"],
                "provider": projected["provider"],
                "provider_model": projected["provider_model"],
            }
        )
    except (JournalError, TransportError) as exc:
        raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID") from exc
    if projected["status"] != projected["execution_status"]:
        raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID")
    provider_evidence_fields = (
        "provider_request_id",
        "provider_response_id",
        "provider_response_sha256",
        "call_started_at",
        "provider_returned_at",
        "committed_at",
    )
    if projected["status"] == "success":
        if not projected["provider_called"] or projected["authoritative_success"] is None:
            raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID")
        try:
            success = _CanonicalAuthoritativeSuccess.from_mapping(
                projected["authoritative_success"]
            )
            success = validate_authoritative_success(success, identity)
        except (JournalError, TransportError) as exc:
            raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID") from exc
        for field_name in (
            "provider_request_id",
            "provider_response_id",
            "provider_response_sha256",
            "response_sha256",
            "call_started_at",
            "provider_returned_at",
            "committed_at",
            "execution_status",
        ):
            if projected[field_name] != getattr(success, field_name):
                raise TransportError("FORMAL_RESULT_PROVENANCE_INVALID")
        projected["authoritative_success"] = success.to_dict()
    else:
        if (
            projected["provider_called"]
            or projected["authoritative_success"] is not None
            or any(projected[field_name] is not None for field_name in provider_evidence_fields)
        ):
            raise TransportError("LOCAL_PROVIDER_EVIDENCE_INVALID")
    if (
        "retrieved_document_ids" in projected
        and "retrieved_scores" in projected
        and len(projected["retrieved_document_ids"]) != len(projected["retrieved_scores"])
    ):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    if not _valid_projection_rq_matrix(projected):
        raise TransportError("UNSAFE_RESULT_PROJECTION")
    return projected


def _retry_classification(
    *,
    status_code: int | None = None,
    category: str | None = None,
    pre_send: bool = False,
) -> str:
    if type(pre_send) is not bool:
        return "terminal"
    if status_code is not None and type(status_code) is not int:
        return "terminal"
    if pre_send or status_code == 429 or (
        status_code is not None and 500 <= status_code <= 599
    ) or category == "temporary_unavailable":
        return "retryable"
    if category in {
        "timeout",
        "read_timeout",
        "connection_reset",
        "broken_pipe",
        "connection_error",
        "uncertain",
    }:
        return "uncertain"
    return "terminal"


def retry_classification(
    *,
    status_code: int | None = None,
    category: str | None = None,
    pre_send: bool = False,
) -> str:
    return _retry_classification(
        status_code=status_code, category=category, pre_send=pre_send
    )


def may_retry(attempt_number: int, classification: str) -> bool:
    return (
        type(attempt_number) is int
        and 1 <= attempt_number < _MAX_ATTEMPTS
        and classification == "retryable"
    )
