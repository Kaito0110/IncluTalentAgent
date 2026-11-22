from auth import (
    SESSION_COOKIE,
    SESSION_LIFETIME,
    _check_auth_rate_limit,
    _clear_auth_rate_limit,
    _normalize_email,
    _password_digest,
    _record_failed_auth,
    authenticate_token,
    login_user,
    register_user,
    revoke_token,
)
from catalog import ACCOMMODATIONS, DEFAULT_PROFILE, JOBS, QUESTION_BANK
from http_server import AppHandler, create_server
from interview_agent import (
    AGENT_NAME,
    answer_interview,
    build_interview_plan,
    evaluate_answer,
    start_interview,
)
from jobs import match_jobs
import persistence
from profiles import delete_profile, get_state, save_profile


ROOT = persistence.ROOT
DATA_FILE = persistence.DATA_FILE
STORE_LOCK = persistence.STORE_LOCK


def main():
    persistence.run_store_initializer()
    server = create_server()
    print("IncluTalent Agent disponible en http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
