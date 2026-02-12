import traceback

try:
    import flask_bcrypt
    print('flask_bcrypt dir:', [d for d in dir(flask_bcrypt) if not d.startswith('__')])
    from flask_bcrypt import Bcrypt
    print('Bcrypt OK:', Bcrypt)
except Exception:
    print('flask_bcrypt error:')
    traceback.print_exc()

try:
    import flask_session
    print('flask_session dir:', [d for d in dir(flask_session) if not d.startswith('__')])
    from flask_session import Session
    print('Session OK:', Session)
except Exception:
    print('flask_session error:')
    traceback.print_exc()
