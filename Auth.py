import os
import re

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from db import first_row, get_supabase_client

load_dotenv()

SUPABASE_PASSWORD_RESET_REDIRECT = os.getenv("SUPABASE_PASSWORD_RESET_REDIRECT")
OFFICIAL_ADMIN_USERNAME = "CampusBeatsOfficial"


def valid_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email) is not None


def strong_password(password):
    return len(password) >= 8


def normalize_email(email):
    return email.strip().lower()


def normalize_username(username):
    return username.strip()


def is_official_admin_username(username):
    return normalize_username(username).casefold() == OFFICIAL_ADMIN_USERNAME.casefold()


def _auth_metadata_username(auth_user):
    metadata = getattr(auth_user, "user_metadata", None) or {}
    if isinstance(metadata, dict):
        username = metadata.get("username")
        if username:
            return normalize_username(username)
    return None


def _resolved_username(auth_user, username_hint=None):
    if username_hint:
        return normalize_username(username_hint)

    metadata_username = _auth_metadata_username(auth_user)
    if metadata_username:
        return metadata_username

    email = getattr(auth_user, "email", None)
    if email:
        return email.split("@")[0]

    return "user"


def _format_auth_error(error):
    message = str(error)
    if "column users.email does not exist" in message:
        return (
            "Your Supabase public.users table is missing the `email` column. "
            "Run the SQL in `supabase_public_users_migration.sql` and try again."
        )
    if 'row-level security policy for table "users"' in message:
        return (
            "Your Supabase public.users table is blocked by RLS. "
            "Run the RLS policies in `supabase_public_users_migration.sql` and try again."
        )
    if "Public users row is not linked correctly" in message:
        return message
    return message


def init_auth_session():
    defaults = {
        "logged_in": False,
        "user_id": None,
        "username": None,
        "role": None,
        "signup_pending_email": None,
        "signup_pending_username": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _fetch_user_by_email(supabase, email):
    return first_row(
        supabase.table("users").select("*").eq("email", email).limit(1).execute()
    )


def _fetch_user_by_id(supabase, user_id):
    return first_row(
        supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    )


def _fetch_user_by_username(supabase, username):
    return first_row(
        supabase.table("users").select("*").eq("username", username).limit(1).execute()
    )


def _persist_login(cookies, user, session):
    access_token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)

    st.session_state["logged_in"] = True
    st.session_state["user_id"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["role"] = user.get("role", "student")
    st.session_state["page"] = "app"

    cookies["user_id"] = str(user["id"])
    cookies["username"] = user["username"]
    cookies["role"] = user.get("role", "student")
    cookies["access_token"] = access_token or ""
    cookies["refresh_token"] = refresh_token or ""
    cookies.save()

    st.session_state["signup_pending_email"] = None
    st.session_state["signup_pending_username"] = None


def _resend_signup_confirmation(supabase, email):
    payload = {
        "type": "signup",
        "email": email,
    }
    if SUPABASE_PASSWORD_RESET_REDIRECT:
        payload["options"] = {"email_redirect_to": SUPABASE_PASSWORD_RESET_REDIRECT}
    supabase.auth.resend(payload)


def _signup_redirect_options():
    if SUPABASE_PASSWORD_RESET_REDIRECT:
        return {"email_redirect_to": SUPABASE_PASSWORD_RESET_REDIRECT}
    return None


def sync_auth_redirect_from_url():
    components.html(
        """
        <script>
        const parentUrl = new URL(window.parent.location.href);
        const hash = parentUrl.hash ? parentUrl.hash.substring(1) : "";
        if (
          hash &&
          (
            hash.includes("type=recovery") ||
            hash.includes("access_token=") ||
            hash.includes("refresh_token=") ||
            hash.includes("token_hash=") ||
            hash.includes("code=")
          )
        ) {
          const params = new URLSearchParams(hash);
          const url = new URL(window.parent.location.href);
          for (const [key, value] of params.entries()) {
            url.searchParams.set(key, value);
          }
          url.hash = "";
          window.parent.location.replace(url.toString());
        }
        </script>
        """,
        height=0,
    )


def maybe_route_password_reset():
    query_params = st.query_params
    recovery_type = query_params.get("type")
    access_token = query_params.get("access_token")
    refresh_token = query_params.get("refresh_token")
    token_hash = query_params.get("token_hash")
    code = query_params.get("code")

    if (
        recovery_type == "recovery"
        or (access_token and refresh_token)
        or token_hash
        or code
    ):
        st.session_state["page"] = "reset_password"


def _clear_auth_query_params():
    for key in list(st.query_params.keys()):
        del st.query_params[key]


def _ensure_local_user(supabase, auth_user, username_hint=None):
    auth_user_id = str(auth_user.id)
    email = auth_user.email
    email_verified = bool(getattr(auth_user, "email_confirmed_at", None))
    resolved_username = _resolved_username(auth_user, username_hint=username_hint)

    existing_user = _fetch_user_by_id(supabase, auth_user_id)
    if not existing_user and email:
        existing_by_email = _fetch_user_by_email(supabase, email)
        if existing_by_email and str(existing_by_email["id"]) != auth_user_id:
            raise ValueError(
                "Public users row is not linked correctly. Expected public.users.id to match auth.users.id."
            )
        existing_user = existing_by_email

    if existing_user:
        existing_username = normalize_username(existing_user.get("username") or "")
        resolved_role = (
            "admin"
            if is_official_admin_username(resolved_username)
            or is_official_admin_username(existing_username)
            else existing_user.get("role", "student")
        )
        updated = (
            supabase.table("users")
            .update(
                {
                    "username": resolved_username or existing_username,
                    "email": email,
                    "email_verified": email_verified,
                    "role": resolved_role,
                }
            )
            .eq("id", existing_user["id"])
            .execute()
        )
        return first_row(updated) or {
            **existing_user,
            "username": resolved_username or existing_username,
            "email": email,
            "email_verified": email_verified,
            "role": resolved_role,
        }

    username = resolved_username
    role = "admin" if is_official_admin_username(username) else "student"
    created = (
        supabase.table("users")
        .insert(
            {
                "id": auth_user_id,
                "username": username,
                "email": email,
                "email_verified": email_verified,
                "role": role,
            }
        )
        .execute()
    )
    user = first_row(created)

    admin_user = first_row(
        supabase.table("users").select("id").eq("role", "admin").order("id").limit(1).execute()
    )
    if user and admin_user:
        supabase.table("follows").upsert(
            {"follower_id": user["id"], "following_id": admin_user["id"]},
            on_conflict="follower_id,following_id",
        ).execute()

    return user


def restore_supabase_session(cookies):
    access_token = cookies.get("access_token")
    refresh_token = cookies.get("refresh_token")

    if not access_token or not refresh_token:
        return False

    try:
        supabase = get_supabase_client()
        session_response = supabase.auth.set_session(access_token, refresh_token)
        auth_user = session_response.user
        auth_session = session_response.session

        if not auth_user:
            return False

        user = _ensure_local_user(supabase, auth_user)
        if not user:
            return False

        st.session_state["logged_in"] = True
        st.session_state["user_id"] = user["id"]
        st.session_state["username"] = user["username"]
        st.session_state["role"] = user.get("role", "student")
        st.session_state["page"] = "app"

        if auth_session:
            cookies["access_token"] = getattr(auth_session, "access_token", "") or ""
            cookies["refresh_token"] = getattr(auth_session, "refresh_token", "") or ""
            cookies["user_id"] = str(user["id"])
            cookies["username"] = user["username"]
            cookies["role"] = user.get("role", "student")
            cookies.save()

        return True
    except Exception:
        return False


def signup_page(cookies):
    st.title("Create Account")

    username = st.text_input("Username", key="signup_username_input")
    email = st.text_input("Email", key="signup_email_input")
    password = st.text_input("Password", type="password", key="signup_password_input")

    normalized_email = normalize_email(email) if email else ""
    pending_email = st.session_state.get("signup_pending_email") or normalized_email
    if pending_email and valid_email(pending_email):
        if st.session_state.get("signup_pending_email"):
            st.info(f"Waiting for email confirmation for `{pending_email}`.")
        if st.button("Resend Confirmation Link", use_container_width=True):
            try:
                supabase = get_supabase_client()
                _resend_signup_confirmation(supabase, pending_email)
                st.session_state["signup_pending_email"] = pending_email
                st.success("Confirmation link resent. Check your email.")
            except Exception as e:
                st.error(f"Could not resend confirmation link: {_format_auth_error(e)}")

    if st.button("Create Account"):
        username = normalize_username(username)
        email = normalize_email(email)

        if not username or not email or not password:
            st.error("Please fill all fields")
            return

        if not valid_email(email):
            st.error("Enter a valid email address")
            return

        if not strong_password(password):
            st.error("Password must be at least 8 characters long")
            return

        try:
            supabase = get_supabase_client()

            if _fetch_user_by_username(supabase, username):
                st.error("Username already exists")
                return

            if _fetch_user_by_email(supabase, email):
                st.error("Email already registered")
                return

            auth_response = supabase.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {"username": username},
                        **(_signup_redirect_options() or {}),
                    },
                }
            )

            auth_user = getattr(auth_response, "user", None)
            auth_session = getattr(auth_response, "session", None)

            if not auth_user:
                st.error("Sign up failed. Please try again.")
                return

            if auth_session:
                user = _ensure_local_user(supabase, auth_user, username_hint=username)
                _persist_login(cookies, user, auth_session)
                st.success("Account created successfully!")
                st.rerun()
            else:
                st.session_state["signup_pending_email"] = email
                st.session_state["signup_pending_username"] = username
                st.success(
                    "Account created. Check your email to confirm your account, then log in with your email once. "
                    "After that, username login will work too."
                )
        except Exception as e:
            if "Error sending confirmation email" in str(e) and email:
                st.session_state["signup_pending_email"] = email
                st.session_state["signup_pending_username"] = username
            st.error(f"Sign up failed: {_format_auth_error(e)}")


def login_page(cookies):
    st.title("Login")

    identifier = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col_spacer, col2 = st.columns([1, 4, 1])

    with col1:
        login_clicked = st.button("Login", use_container_width=True)

    with col_spacer:
        st.empty()

    with col2:
        forgot_clicked = st.button("Forgot Password?", use_container_width=True)

    if login_clicked:
        identifier = identifier.strip()

        if not identifier or not password:
            st.warning("Please enter both fields")
            return

        try:
            supabase = get_supabase_client()
            login_email = normalize_email(identifier)

            if not valid_email(login_email):
                user_row = _fetch_user_by_username(supabase, normalize_username(identifier))
                if not user_row:
                    st.error(
                        "Username login is not available yet for this account. "
                        "After email verification, log in with your email once first."
                    )
                    return
                if not user_row.get("email"):
                    st.error("This account is missing an email in public.users. Please re-run the users table migration.")
                    return
                login_email = user_row["email"]

            auth_response = supabase.auth.sign_in_with_password(
                {"email": login_email, "password": password}
            )

            auth_user = getattr(auth_response, "user", None)
            auth_session = getattr(auth_response, "session", None)

            if not auth_user or not auth_session:
                st.error("Login failed. Please check your credentials.")
                return

            user = _ensure_local_user(supabase, auth_user)
            _persist_login(cookies, user, auth_session)
            st.success("Login successful!")
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {_format_auth_error(e)}")

    if forgot_clicked:
        st.session_state["page"] = "forgot"
        st.rerun()


def forgot_password_page():
    st.title("Forgot Password")
    st.caption("Supabase Auth will send a password reset link to your email.")

    email = st.text_input("Enter your registered email", key="forgot_email")

    if st.button("Send Reset Link"):
        if not email or not valid_email(email):
            st.error("Enter a valid email address")
            return

        try:
            supabase = get_supabase_client()
            if SUPABASE_PASSWORD_RESET_REDIRECT:
                supabase.auth.reset_password_for_email(
                    email,
                    {"redirect_to": SUPABASE_PASSWORD_RESET_REDIRECT},
                )
            else:
                supabase.auth.reset_password_for_email(email)
            st.success("Password reset link sent. Check your email.")
        except Exception as e:
            st.error(f"Could not send reset link: {_format_auth_error(e)}")


def reset_password_page(cookies):
    st.markdown(
        """
        <style>
        .cb-reset-shell {
            max-width: 720px;
            margin: 1rem auto 0 auto;
            padding: 1.4rem;
            border-radius: 28px;
            background:
                radial-gradient(circle at top left, rgba(155, 200, 112, 0.22), transparent 28%),
                radial-gradient(circle at bottom right, rgba(148, 205, 216, 0.24), transparent 30%),
                linear-gradient(145deg, rgba(255,255,255,0.94), rgba(239,248,244,0.95));
            border: 1px solid rgba(107, 181, 166, 0.24);
            box-shadow: 0 18px 40px rgba(52, 93, 83, 0.12);
        }
        .cb-reset-kicker {
            display: inline-block;
            padding: .3rem .75rem;
            border-radius: 999px;
            background: rgba(24, 68, 61, 0.08);
            color: #21584e;
            font-size: .8rem;
            font-weight: 700;
            margin-bottom: .75rem;
        }
        .cb-reset-title {
            margin: 0;
            color: #123d36;
            font-size: clamp(1.9rem, 3vw, 2.8rem);
            line-height: 1;
        }
        .cb-reset-copy {
            margin: .8rem 0 0 0;
            color: #3d655d;
            font-size: .98rem;
        }
        .cb-reset-note {
            margin-top: 1rem;
            padding: .85rem 1rem;
            border-radius: 18px;
            background: rgba(255,255,255,0.75);
            border: 1px solid rgba(107, 181, 166, 0.16);
            color: #487168;
            font-size: .92rem;
        }
        </style>
        <div class="cb-reset-shell">
            <div class="cb-reset-kicker">Secure password reset</div>
            <h1 class="cb-reset-title">Choose a new password</h1>
            <p class="cb-reset-copy">
                Create a fresh password for your Campus Beats account and jump back in.
            </p>
            <div class="cb-reset-note">
                Use at least 8 characters and make sure both password fields match exactly.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    access_token = st.query_params.get("access_token")
    refresh_token = st.query_params.get("refresh_token")
    recovery_type = st.query_params.get("type")
    token_hash = st.query_params.get("token_hash")
    code = st.query_params.get("code")

    if not (
        recovery_type == "recovery"
        or (access_token and refresh_token)
        or token_hash
        or code
    ):
        st.warning("This reset link is invalid or expired. Please request a new password reset email.")
        if st.button("Back to Login"):
            st.session_state["page"] = "login"
            st.rerun()
        return

    st.write("")
    new_password = st.text_input("Enter New Password", type="password", key="reset_new_password")
    confirm_password = st.text_input("Re-enter Password", type="password", key="reset_confirm_password")

    if st.button("Update Password", use_container_width=True):
        if not new_password or not confirm_password:
            st.error("Please fill both fields.")
            return

        if not strong_password(new_password):
            st.error("Password must be at least 8 characters long")
            return

        if new_password != confirm_password:
            st.error("Passwords do not match")
            return

        try:
            supabase = get_supabase_client()
            session_response = None

            if access_token and refresh_token:
                session_response = supabase.auth.set_session(access_token, refresh_token)
            elif token_hash:
                session_response = supabase.auth.verify_otp(
                    {
                        "token_hash": token_hash,
                        "type": "recovery",
                    }
                )
            elif code:
                session_response = supabase.auth.exchange_code_for_session(code)

            if not session_response or not getattr(session_response, "session", None):
                st.error("This reset session is invalid or expired. Please request a new reset link.")
                return

            supabase.auth.update_user({"password": new_password})
            supabase.auth.sign_out()

            if cookies is not None:
                cookies["access_token"] = ""
                cookies["refresh_token"] = ""
                cookies.save()

            _clear_auth_query_params()
            st.session_state["page"] = "login"
            st.success("Password updated successfully. Please log in with your new password.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not update password: {_format_auth_error(e)}")


def logout(cookies):
    try:
        access_token = cookies.get("access_token")
        refresh_token = cookies.get("refresh_token")
        if access_token and refresh_token:
            supabase = get_supabase_client()
            supabase.auth.set_session(access_token, refresh_token)
            supabase.auth.sign_out()
    except Exception:
        pass

    st.session_state["logged_in"] = False
    st.session_state["user_id"] = None
    st.session_state["username"] = None
    st.session_state["role"] = None
    st.session_state["page"] = "landing"
    st.session_state["tracks"] = []
    st.session_state["feed_view_mode"] = "all"
    st.session_state["show_followers_list"] = False
    st.session_state["show_following_list"] = False
    st.session_state["signup_pending_email"] = None
    st.session_state["signup_pending_username"] = None

    cookies["user_id"] = ""
    cookies["username"] = ""
    cookies["role"] = ""
    cookies["current_menu"] = ""
    cookies["access_token"] = ""
    cookies["refresh_token"] = ""
    cookies.save()
