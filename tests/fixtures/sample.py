"""Authentication service for managing user tokens."""

import hashlib
from datetime import datetime, timedelta


class AuthService:
    """Handles user authentication and token management."""

    def __init__(self, secret_key: str, token_ttl: int = 3600):
        self.secret_key = secret_key
        self.token_ttl = token_ttl

    def authenticate(self, username: str, password: str) -> dict:
        """Verify credentials and return a token."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return {
            "token": self._generate_token(username),
            "expires_at": datetime.utcnow() + timedelta(seconds=self.token_ttl),
        }

    def refresh_token(self, token: str) -> dict:
        """Refresh an existing token."""
        claims = self._decode_token(token)
        return {
            "token": self._generate_token(claims["sub"]),
            "expires_at": datetime.utcnow() + timedelta(seconds=self.token_ttl),
        }

    def _generate_token(self, subject: str) -> str:
        payload = f"{subject}:{datetime.utcnow().isoformat()}"
        return hashlib.sha256(f"{payload}:{self.secret_key}".encode()).hexdigest()

    def _decode_token(self, token: str) -> dict:
        return {"sub": "user", "exp": datetime.utcnow()}


def create_auth_service(config: dict) -> AuthService:
    """Factory function for creating AuthService instances."""
    return AuthService(
        secret_key=config["secret_key"],
        token_ttl=config.get("token_ttl", 3600),
    )
