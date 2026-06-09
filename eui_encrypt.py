"""Xiaomi EUI form field encryption — pure Python (no Node.js dependency)"""
import os
import base64
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Util.Padding import pad

RSA_PUBKEY_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYEVrK/4Mahiv0pUJgTybx4J9P
5dUT/Y0PuwMbk+gMU+jrZnBiXGv6/hCH1avIhoBcE535F8nJQQN3UavZdFkYidso
XuEnat3+eVTp3FslyhRwIBDF09v4vDhRtxFOT+R7uH7h/mzmyA2/+lfIMWGIrffX
prYizbV76+YQKhoqFQIDAQAB
-----END PUBLIC KEY-----"""

AES_IV = b"0102030405060708"
KEY_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"


def _random_aes_key(length=16):
    return "".join(KEY_CHARS[os.urandom(1)[0] % len(KEY_CHARS)] for _ in range(length))


def encrypt_form_fields(fields: dict) -> dict:
    """
    Encrypt form fields exactly like Xiaomi browser JS.
    Returns {"EUI": "rsa_key.b64_field_names", "encryptedParams": {"field": "base64_ciphertext"}}
    """
    aes_key = _random_aes_key()
    key_bytes = aes_key.encode("utf-8")

    # Encrypt each field with AES-128-CBC PKCS7
    encrypted_params = {}
    for name, value in fields.items():
        cipher = AES.new(key_bytes, AES.MODE_CBC, AES_IV)
        ct = cipher.encrypt(pad(value.encode("utf-8"), AES.block_size))
        encrypted_params[name] = base64.b64encode(ct).decode("utf-8")

    # RSA encrypt the base64-encoded AES key
    key_b64 = base64.b64encode(key_bytes).decode("utf-8")
    rsa_key = RSA.import_key(RSA_PUBKEY_PEM)
    rsa_cipher = PKCS1_v1_5.new(rsa_key)
    rsa_ct = rsa_cipher.encrypt(key_b64.encode("utf-8"))
    rsa_encrypted = base64.b64encode(rsa_ct).decode("utf-8")

    # EUI = rsa_encrypted_key + "." + base64(field_names)
    field_names_b64 = base64.b64encode(",".join(fields.keys()).encode("utf-8")).decode("utf-8")
    eui = rsa_encrypted + "." + field_names_b64

    return {"EUI": eui, "encryptedParams": encrypted_params}


if __name__ == "__main__":
    import sys, json
    fields = json.loads(sys.argv[1])
    print(json.dumps(encrypt_form_fields(fields)))
