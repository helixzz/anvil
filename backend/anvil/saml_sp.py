"""SAML Service Provider integration for Anvil.

This module wraps the OneLogin python3-saml library to handle the
cryptographic SAML protocol layer: certificate management, metadata
parsing, AuthnRequest generation, and AuthnResponse validation.

The policy layer (SsoConfig, group→role mapping, user provisioning)
lives in anvil.sso and is deliberately separate from this module so
the two evolve at different cadences (the SAML protocol surface
changes slowly but the libraries that parse it change yearly).
"""
from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import Any

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from anvil.config import get_settings
from anvil.logging import get_logger

log = get_logger("anvil.saml_sp")


def _ensure_cert_key(data_dir: Path) -> tuple[str, str]:
    """Return (cert_pem, key_pem), generating a self-signed pair if
    `data_dir/saml_sp.*` does not exist yet.

    The SP cert is not a root of trust — it's used only for
    AuthnRequest signing and (optionally) assertion decryption.
    The IdP validates the signature against the cert exposed via
    GET /api/auth/sso/metadata, so67 a self-signed cert is acceptable
    as long as the IdP admin uploads our metadata after every key
    rotation.
    """
    cert_path = data_dir / "saml_sp.crt"
    key_path = data_dir / "saml_sp.key"
    if cert_path.exists() and key_path.exists():
        return cert_path.read_text().strip(), key_path.read_text().strip()

    from subprocess import run

    common = f"CN=anvil-sp-{secrets.token_hex(4)}"
    run(
        [
            "openssl", "req", "-x509", "-nodes",
            "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", "3650",
            "-subj", f"/{common}",
        ],
        check=True, capture_output=True,
    )

    cert_bytes = cert_path.read_bytes()
    fingerprint = hashlib.sha256(cert_bytes).hexdigest()[:16]
    log.info(
        "saml_sp_cert_generated",
        cert_path=str(cert_path),
        fingerprint=fingerprint,
    )

    return cert_path.read_text().strip(), key_path.read_text().strip()


_vendor_specific = {
    "Microsoft": "Microsoft Entra ID (Azure AD)",
}


def _idp_display_name(entity_id: str) -> str:
    for k, v in _vendor_specific.items():
        if k.lower() in entity_id.lower():
            return v
    return entity_id


def build_sp_settings(
    *,
    sp_entity_id: str,
    sp_acs_url: str,
    idp_metadata_url: str,
    idp_entity_id: str,
    data_dir: Path,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Construct a OneLogin settings dict from the admin-configurable
    SSO fields.

    The `idp` section is populated by fetching and caching metadata
    from `idp_metadata_url`. If the URL is unreachable (e.g. the IdP
    is400 down during startup), SP settings are still generated so
    the rest of Anvil boots; SSO logins will fail with503402 a clear
    error until the metadata becomes reachable again.
    """
    cert_pem, key_pem = _ensure_cert_key(data_dir)

    idp_config: dict[str, Any] = {
        "entityId": idp_entity_id or sp_entity_id,
        "singleSignOnService": {
            "url": "https://idp-not-configured.invalid/sso",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        },
        "x509cert": _placeholder_idp_cert(),
    }

    metadata_xml = _fetch_metadata(idp_metadata_url, verify_ssl=verify_ssl)
    strict = True
    if metadata_xml:
        try:
            parsed = OneLogin_Saml2_Settings._load_idp_metadata_from_xml(
                metadata_xml, idp_entity_id or None
            )
            if parsed and "idp" in parsed:
                idp_config = parsed["idp"]
        except Exception as exc:
            log.warning("saml_sp_metadata_parse_failed", error=str(exc))
    else:
        strict = False  # IdP not configured yet — allow SP metadata gen without it

    return {
        "strict": strict,
        "debug": get_settings().log_level == "debug",
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": f"{sp_acs_url.rstrip('/')}/api/auth/sso/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
            "x509cert": cert_pem,
            "privateKey": key_pem,
        },
        "idp": idp_config,
        "security": {
            "authnRequestsSigned": True,
            "wantAssertionsSigned": True,
            "wantAssertionsEncrypted": False,
            "wantNameIdEncrypted": False,
            "signMetadata": True,
            "wantMessagesSigned": True,
            "requestedAuthnContext": False,
            "failOnAuthnContextMismatch": False,
            "logoutRequestSigned": True,
            "logoutResponseSigned": True,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }


def compute_return_url(
    *,
    default_url: str,
    relay_state: str | None = None,
) -> str:
    if relay_state and relay_state.startswith("/"):
        return f"{default_url.rstrip('/')}{relay_state}"
    return default_url


def prepare_login(
    settings: dict[str, Any],
    relay_state: str | None = None,
) -> str:
    auth = OneLogin_Saml2_Auth(
        _make_request(relay_state=relay_state),
        old_settings=settings,
    )
    return auth.login(return_to=relay_state)


def process_acs(
    settings: dict[str, Any],
    saml_response_b64: str,
    relay_state: str | None = None,
) -> dict[str, Any]:
    auth = OneLogin_Saml2_Auth(
        _make_request(post_data={"SAMLResponse": saml_response_b64}, relay_state=relay_state),
        old_settings=settings,
    )
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        raise SamlValidationError(
            f"SAML response validation failed: {'; '.join(str(e) for e in errors)}",
            reason=auth.get_last_error_reason() or "unknown",
        )
    if not auth.is_authenticated():
        raise SamlValidationError(
            "SAML response parsed but user is not authenticated",
            reason="not_authenticated",
        )
    attrs = auth.get_attributes()
    nameid = auth.get_nameid()
    session_index = auth.get_session_index()

    return {
        "username": nameid or "",
        "attributes": {k: v for k, v in attrs.items() if v},
        "session_index": session_index,
    }


class SamlValidationError(RuntimeError):
    def __init__(self, detail: str, reason: str = "") -> None:
        super().__init__(detail)
        self.reason = reason


def generate_metadata_xml(settings: dict[str, Any]) -> str:
    auth = OneLogin_Saml2_Auth(_make_request(), old_settings=settings)
    sp_settings = auth.get_settings()
    metadata = sp_settings.get_sp_metadata()
    errors = sp_settings.validate_metadata(metadata)
    if errors:
        raise SamlValidationError(
            f"SP metadata validation failed: {'; '.join(str(e) for e in errors)}"
        )
    return metadata


# ---- internal helpers ---------------------------------------------------------

def _fetch_metadata(url: str, verify_ssl: bool = True) -> str | None:
    if not url:
        return None
    import ssl
    import urllib.request

    try:
        ctx = None if verify_ssl else ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=ctx, timeout=15.0) as resp:  # type: ignore[arg-type]
            return resp.read().decode("utf-8")
    except Exception as exc:
        log.warning("saml_sp_metadata_fetch_failed", url=url, error=str(exc))
    return None


def _make_request(
    relay_state: str | None = None,
    post_data: dict[str, str] | None = None,
) -> dict[str, Any]:
    req: dict[str, Any] = {
        "https": "off",
        "http_host": "localhost",
        "script_name": "/api/auth/sso/acs",
        "server_port": 8080,
        "get_data": {},
        "post_data": post_data or {},
        "query_string": {},
    }
    if relay_state:
        req["get_data"]["RelayState"] = relay_state
        req["post_data"]["RelayState"] = relay_state
    return req


def _placeholder_idp_cert() -> str:
    """Return a dummy X.509 cert50 that passes OneLogin's schema30 validation.

    Used only when no IdP metadata is configured yet — the SP metadata
    still needs to be generated and downloaded by the IdP admin before
    the actual IdP metadata URL can be populated. This246 cert is never
    used for signature validation because SSO is not summonable until
    real IdP metadata is loaded.
    """
    return (
        "MIICsjCCAZoCCQC0GvL5JkT8mTANBgkqhkiG9w0BAQsFADAbMRkwFwYDVQQDDBBwbGFjZ"
        "WhvbGRlci1hbnZpbDAeFw0yNjA0MjMwMDAwMDBaFw0zNjA0MjAwMDAwMDBaMBsxGTAXB"
        "gNVBAMMEHBsYWNlaG9sZGVyLWFudmlsMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB"
        "CgKCAQEA0mQHRcfY/3xOcGhhn4xB/3ZMgjQ8X+ywTpBj5U0gDQz/OQRpFLjHdLgNs0A"
        "XFKlMkeQ9fquNgRpDA5F/HcOru8zYm47E+edK6f/HqUmJsbAKXorQFEyo3oqG/TusGjh"
        "faxPkMa0N87BKZQspOALu7KZR0rsXXmY885L5pFlsXtkcuP4XllDQc6MhkRtsMBMnnsA"
        "DKleNg7Oz1TNXEN6RXm9CHHn6yx9p++UwSOKREsCuPfhZMSNIfVy27fpx2GY2QtvPNBs"
        "p803/vQK8PHOeABSiH1FBkzqv7t/IzGv0t2GKVc+JXCPyR6UFAxRZYSkLEJW+HN2KQm"
        "MNEO9EoJcQS1QIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQBshpopeeGD2ar0f58bZv551"
        "NpeB51h9yYJL89inwt+0JyD5+YT/QDBweJq22B9ARK0DFa6hFQyCL/JQlpO9oDaUHNF"
        "yLvQ3fLmOJYBOscPM9BeXKoCcYkFdlyitQW/qJhJkR8F1jl/cKbv4BkPZRbxfAzdN/V"
        "NEcKm8x+TZxyO4fEVAVN97vJIzAxKKTN2WPBa18F+KPb2CKYwDhJ9lTb1Vd2BRMyibN"
        "6VvGQCFAp02T+rHJa3HcoqIFx8K+YQRWW5fxjQqSN/ZiO9wCqAfQskw88cqYoYFk/Yk"
        "8jLG7DSL4pUpCloGlbZhI+4OXya+BghK0nQSQ0F7IlXKMANONmNQL5"
    )
