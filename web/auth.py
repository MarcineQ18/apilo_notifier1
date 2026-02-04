from functools import wraps
from flask import request, Response
from settings import ADMIN_USER, ADMIN_PASS


def require_basic_auth(admin_user: str, admin_pass: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.authorization
            if not auth or auth.username != admin_user or auth.password != admin_pass:
                return Response("Auth required", 401, {"WWW-Authenticate": 'Basic realm="Login"'})
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# GOTOWY dekorator używany w UI
auth = require_basic_auth(ADMIN_USER, ADMIN_PASS)
