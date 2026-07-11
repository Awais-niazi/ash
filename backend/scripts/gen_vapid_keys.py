"""
Generate a VAPID keypair for Web Push, printed as base64url strings ready to
paste into .env. Run once; use the SAME keys on both laptop and server (they
identify Ash's push, and existing subscriptions are bound to the public key).

    venv/bin/python scripts/gen_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def main():
    key = ec.generate_private_key(ec.SECP256R1())

    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )  # 65-byte uncompressed point — this is the browser applicationServerKey

    print("# Add these to backend/.env (same values on laptop and server):")
    print(f"VAPID_PUBLIC_KEY={b64url(public_raw)}")
    print(f"VAPID_PRIVATE_KEY={b64url(private_raw)}")
    print("VAPID_SUBJECT=mailto:awaisfaiz101@gmail.com")


if __name__ == "__main__":
    main()
