import base64
import hashlib

from config import Config

try:
    from cryptography.fernet import Fernet, InvalidToken
    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency should exist in production
    Fernet = None
    InvalidToken = Exception
    CRYPTO_AVAILABLE = False


ENCRYPTED_PREFIX = 'enc::'


def _get_fernet():
    """Create a deterministic Fernet instance from configured app secrets."""
    seed = (Config.SECRET_ENCRYPTION_KEY or Config.SECRET_KEY or '').encode('utf-8')
    digest = hashlib.sha256(seed).digest()
    key = base64.urlsafe_b64encode(digest)
    if not CRYPTO_AVAILABLE:
        raise RuntimeError('cryptography package is required for secret encryption')
    return Fernet(key)


def encrypt_secret(value):
    """Encrypt a secret value for storage."""
    if value in [None, '']:
        return ''
    token = _get_fernet().encrypt(str(value).encode('utf-8')).decode('utf-8')
    return f'{ENCRYPTED_PREFIX}{token}'


def decrypt_secret(value):
    """Decrypt a secret value from storage, supporting legacy plaintext values."""
    if value in [None, '']:
        return ''
    text = str(value)
    if not text.startswith(ENCRYPTED_PREFIX):
        return text
    token = text[len(ENCRYPTED_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise ValueError('Unable to decrypt stored secret') from exc
