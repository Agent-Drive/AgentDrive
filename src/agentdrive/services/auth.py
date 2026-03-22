import bcrypt


def hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    return bcrypt.checkpw(key.encode(), hashed.encode())
