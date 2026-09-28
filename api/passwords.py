"""
Password hashing for api/routers/auth.py's signup/login. Uses bcrypt
(already an installed dependency, purpose-built for this — not a
hand-rolled scheme) with its own per-password random salt baked into the
returned hash string. Never store, log, or compare a plaintext password.
"""

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        # Malformed/foreign hash format — fail closed rather than raise.
        return False
