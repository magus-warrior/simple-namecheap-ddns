"""Security helpers for encryption/decryption."""

from cryptography.fernet import Fernet


class CryptoManager:
    """Encrypts and decrypts strings using a base64-encoded Fernet key."""

    def __init__(self, base64_key: str) -> None:
        self._fernet = Fernet(base64_key.encode("utf-8"))

    def encrypt_str(self, text: str) -> str:
        """Encrypt a string and return the cipher text as a string."""
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt_str(self, cipher: str) -> str:
        """Decrypt a cipher text string and return the original string."""
        return self._fernet.decrypt(cipher.encode("utf-8")).decode("utf-8")
