from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from l9_debt_intelligence.snapshots.hashing import namespaced_document_hash

from .errors import SignatureVerificationError

#: Namespace for the signer key identity. Consumer-defined, not ours to choose.
#:
#: `l9-ci-debt-lsp` resolves the trusted verification key by this id
#: (`packs/trust.py::public_key_id`, `packs/installer.py`), and its registry
#: loader recomputes the id from each trusted key and refuses a mismatch. So the
#: derivation here must stay byte-identical to the consumer's: the same
#: `key_` prefix, the same single-key document `{"raw_public_key": <hex>}`, and
#: the same canonical JSON encoding -- which both repositories already spell
#: identically (sorted keys, no spaces, `ensure_ascii=False`, `allow_nan=False`).
#:
#: Deriving it rather than storing it is deliberate: an id carried alongside the
#: key could drift from the key it names, and the consumer would then reject a
#: correctly signed pack for a reason no one could see in the manifest.
_KEY_ID_PREFIX = "key_"
_ED25519_PUBLIC_KEY_BYTES = 32


def public_key_id(public_key_base64: str) -> str:
    """The signer key identity for a base64 Ed25519 public key.

    Mirrors `l9_debt_lsp.packs.trust.public_key_id`. See `_KEY_ID_PREFIX` for
    why this is a mirror rather than an independent choice.
    """
    try:
        raw = base64.b64decode(public_key_base64.encode("ascii"), validate=True)
    except Exception as error:  # noqa: BLE001 - re-raised as a contract error
        raise SignatureVerificationError("public key is not valid base64") from error
    if len(raw) != _ED25519_PUBLIC_KEY_BYTES:
        raise SignatureVerificationError(
            f"Ed25519 public key must be {_ED25519_PUBLIC_KEY_BYTES} bytes"
        )
    return namespaced_document_hash(_KEY_ID_PREFIX, {"raw_public_key": raw.hex()})


@dataclass(frozen=True)
class DetachedSignature:
    algorithm: str
    signature: str
    public_key: str

    def as_dict(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "signature": self.signature,
            "public_key": self.public_key,
        }


def _discard(path: Path) -> None:
    """Best-effort removal during cleanup, never masking the original error.

    Cleanup that can itself raise is not cleanup: the first attempt at this
    called `Path.unlink` directly, and when the private key path was a
    directory the `IsADirectoryError` from the cleanup escaped and left the
    public half on disk -- the exact orphan the cleanup existed to prevent.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def generate_keypair(
    *,
    private_key_path: Path,
    public_key_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    # Both paths are written or neither is. A private key left behind by a
    # half-finished keygen is worse than no key: the caller sees a failure and
    # has no reason to look for the file, so signing material accumulates
    # unnoticed. The public key is written first because it is the harmless
    # half; if that fails, nothing secret has been created yet.
    public_key_path.write_bytes(public_bytes)
    try:
        private_key_path.write_bytes(private_bytes)
        private_key_path.chmod(0o600)
    except OSError:
        _discard(private_key_path)
        _discard(public_key_path)
        raise


def load_private_key(path: Path) -> Ed25519PrivateKey:
    value = serialization.load_pem_private_key(
        path.read_bytes(),
        password=None,
    )
    if not isinstance(value, Ed25519PrivateKey):
        raise TypeError("private key must be Ed25519")
    return value


def load_public_key_bytes(value: str) -> Ed25519PublicKey:
    decoded = base64.b64decode(value.encode("ascii"))
    key = Ed25519PublicKey.from_public_bytes(decoded)
    return key


def sign_digest(
    digest_hex: str,
    private_key_path: Path,
) -> DetachedSignature:
    private_key = load_private_key(private_key_path)
    digest = bytes.fromhex(digest_hex)
    signature = private_key.sign(digest)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return DetachedSignature(
        algorithm="Ed25519",
        signature=base64.b64encode(signature).decode("ascii"),
        public_key=base64.b64encode(public_key).decode("ascii"),
    )


def verify_digest(
    *,
    digest_hex: str,
    signature: str,
    public_key: str,
) -> None:
    try:
        load_public_key_bytes(public_key).verify(
            base64.b64decode(signature.encode("ascii")),
            bytes.fromhex(digest_hex),
        )
    except Exception as error:
        raise SignatureVerificationError(
            "defense-pack signature verification failed"
        ) from error
