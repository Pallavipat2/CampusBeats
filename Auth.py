import random
import re
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime, timedelta

import bcrypt
import streamlit as st
from dotenv import load_dotenv

from db import get_connection

load_dotenv()

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")


# ---------------- PASSWORD HELPERS ----------------

def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


# ---------------- VALIDATION ----------------

def valid_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email) is not None


def strong_password(password):
    return len(password) >= 8


def generate_otp():
    return str(random.randint(100000, 999999))


# ---------------- EMAIL SENDER ----------------

def send_email_otp(receiver_email, otp, purpose="verification"):
    sender_email = EMAIL_USER
    sender_password = EMAIL_PASS

    if not sender_email or not sender_password:
        st.error("Email sender is not configured. Check EMAIL_USER and EMAIL_PASS in .env")
        return False

    if purpose == "verification":
        subject = "Campus Beats Email Verification Code"
        body = f"""
Hello,

Your Campus Beats verification code is: {otp}

This code expires in 10 minutes.

- Campus Beats
"""
    else:
        subject = "Campus Beats Password Reset Code"
        body = f"""
Hello,

Your Campus Beats password reset code is: {otp}

This code expires in 10 minutes.

- Campus Beats
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False
# ---------------- SESSION DEFAULTS ----------------

def init_auth_session():

    defaults = {
        "signup_otp_sent": False,
        "signup_pending": None,
        "reset_otp_sent": False,
        "reset_pending_email": None,
         "reset_otp": None,
        "reset_otp_expiry": None,
        "reset_stage": "email",
        "reset_last_sent_email": None,
        "logged_in": False,
        "user_id": None,
        "username": None,
        "role": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# ---------------- SIGNUP ----------------

def signup_page():
    st.title("Create Account")

    username = st.text_input("Username", key="signup_username_input")
    email = st.text_input("Email", key="signup_email_input")
    password = st.text_input("Password", type="password", key="signup_password_input")

    conn = get_connection()
    if conn is None:
        st.error("Database connection failed")
        st.stop()

    cursor = conn.cursor(dictionary=True)

    if not st.session_state["signup_otp_sent"]:
        if st.button("Send Verification Code"):
            if not username or not email or not password:
                st.error("Please fill all fields")
            elif not valid_email(email):
                st.error("Enter a valid email address")
            elif not strong_password(password):
                st.error("Password must be at least 8 characters long")
            else:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                existing_user = cursor.fetchone()

                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                existing_email = cursor.fetchone()

                if existing_user:
                    st.error("Username already exists")
                elif existing_email:
                    st.error("Email already registered")
                else:
                    otp = generate_otp()
                    sent = send_email_otp(email, otp, purpose="verification")

                    if sent:
                        st.session_state["signup_pending"] = {
                            "username": username,
                            "email": email,
                            "password": password,
                            "otp": otp,
                            "expiry": datetime.now() + timedelta(minutes=10),
                        }
                        st.session_state["signup_otp_sent"] = True
                        st.success("Verification code sent to your email")
                        st.rerun()
                    else:
                        st.error("Could not send verification code")

    else:
        entered_otp = st.text_input("Enter Verification Code", key="signup_otp_input")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Verify and Create Account"):
                pending = st.session_state["signup_pending"]

                if not pending:
                    st.error("Signup session expired. Start again.")
                    st.session_state["signup_otp_sent"] = False
                elif datetime.now() > pending["expiry"]:
                    st.error("Verification code expired. Please request a new code.")
                    st.session_state["signup_otp_sent"] = False
                    st.session_state["signup_pending"] = None
                elif entered_otp != pending["otp"]:
                    st.error("Invalid verification code")
                else:
                    hashed_pw = hash_password(pending["password"])

                    cursor.execute("""
                        INSERT INTO users (username, email, password_hash, email_verified, role)
                        VALUES (%s, %s, %s, %s, %s)
                         """,
                        (pending["username"], pending["email"], hashed_pw, 1, "student"),
                    )
                    new_user_id = cursor.lastrowid

                    cursor.execute("""
                        SELECT id FROM users
                        WHERE role = 'admin'
                        ORDER BY id ASC
                        LIMIT 1
                    """)
                    admin_user = cursor.fetchone()

                    if admin_user:
                        cursor.execute("""
                            INSERT IGNORE INTO follows (follower_id, following_id)
                            VALUES (%s, %s)
                        """, (new_user_id, admin_user["id"]))

                    conn.commit()

                    st.success("Account created successfully! You can now log in.")
                    st.session_state["signup_otp_sent"] = False
                    st.session_state["signup_pending"] = None

        with col2:
            if st.button("Resend Code"):
                st.session_state["signup_otp_sent"] = False
                st.session_state["signup_pending"] = None
                st.rerun()

    cursor.close()
    conn.close()


# ---------------- LOGIN ----------------
def login_page(cookies):

    st.title("Login")

    conn = get_connection()
    if conn is None:
        st.error("Database connection failed")
        st.stop()

    cursor = conn.cursor(dictionary=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Buttons
    col1, col_spacer, col2 = st.columns([1, 4, 1])

    with col1:
        login_clicked = st.button("Login", use_container_width=True)

    with col_spacer:
        st.empty()

    with col2:
        forgot_clicked = st.button("Forgot Password?", use_container_width=True)

    # LOGIN LOGIC (FIXED)
    if login_clicked:
        if username and password:
            try:
                cursor.execute(
                    "SELECT * FROM users WHERE username=%s",
                    (username,)
                )
                user = cursor.fetchone()

                # ✅ FIXED PASSWORD CHECK
                if user and verify_password(password, user["password_hash"]):
                    st.session_state["logged_in"] = True
                    st.session_state["user_id"] = user["id"]
                    st.session_state["username"] = user["username"]
                    st.session_state["role"] = user["role"]
                    st.session_state["page"] = "app"

                    # Save cookies
                    cookies["user_id"] = str(user["id"])
                    cookies["username"] = user["username"]
                    cookies["role"] = user["role"]
                    cookies.save()

                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")

            except Exception as e:
                st.error(f"Database error: {e}")
        else:
            st.warning("Please enter both fields")

    # Forgot password navigation
    if forgot_clicked:
        st.session_state["page"] = "forgot"
        st.rerun()

    cursor.close()
    conn.close()

# ---------------- FORGOT PASSWORD ----------------

def _send_reset_code_if_possible(cursor, email):
    if not valid_email(email):
        return

    if st.session_state.get("reset_last_sent_email") == email and st.session_state.get("reset_otp_sent"):
        return

    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    if not user:
        return

    otp = generate_otp()
    sent = send_email_otp(email, otp, purpose="reset")
    if sent:
        st.session_state["reset_pending_email"] = email
        st.session_state["reset_otp"] = otp
        st.session_state["reset_otp_expiry"] = datetime.now() + timedelta(minutes=10)
        st.session_state["reset_otp_sent"] = True
        st.session_state["reset_stage"] = "verify_code"
        st.session_state["reset_last_sent_email"] = email
        st.rerun()

def forgot_password_page():
    st.title("Forgot Password")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    stage = st.session_state.get("reset_stage", "email")
    if stage == "email":
        email = st.text_input("Enter your registered email", key="forgot_email")

        if email:
            _send_reset_code_if_possible(cursor, email)

        st.info("Enter your registered email. A reset code will be sent automatically once the email is found.")

    elif stage == "verify_code":
        email = st.session_state.get("reset_pending_email", "")
        st.write(f'Enter the reset code sent to your registered email id "{email}"')
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Verify Code"):
                if datetime.now() > st.session_state["reset_otp_expiry"]:
                    st.error("Reset code expired. Please resend the code.")
                elif entered_otp != st.session_state["reset_otp"]:
                    st.error("Invalid reset code")
                else:
                    st.session_state["reset_stage"] = "set_password"
                    st.success("Code verified")
                    st.rerun()

        with col2:
            if st.button("Resend Code"):
                otp = generate_otp()
                sent = send_email_otp(email, otp, purpose="reset")
                if sent:
                    st.session_state["reset_otp"] = otp
                    st.session_state["reset_otp_expiry"] = datetime.now() + timedelta(minutes=10)
                    st.success("New reset code sent")

        with col3:
            if st.button("Back"):
                st.session_state["reset_stage"] = "email"
                st.session_state["reset_otp_sent"] = False
                st.session_state["reset_pending_email"] = None
                st.session_state["reset_otp"] = None
                st.session_state["reset_otp_expiry"] = None
                st.session_state["reset_last_sent_email"] = None
                st.rerun()

    elif stage == "set_password":
        new_password = st.text_input("New Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_password")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Set New Password"):
                if not strong_password(new_password):
                    st.error("Password must be at least 8 characters long")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                else:
                    hashed_pw = hash_password(new_password)

                    cursor.execute("""
                        UPDATE users
                        SET password_hash = %s
                        WHERE email = %s
                    """, (hashed_pw, st.session_state["reset_pending_email"]),)
                    conn.commit()

                    st.success("Password reset successfully! You can now log in.")
                    st.session_state["reset_stage"] = "email"
                    st.session_state["reset_otp_sent"] = False
                    st.session_state["reset_pending_email"] = None
                    st.session_state["reset_otp"] = None
                    st.session_state["reset_otp_expiry"] = None
                    st.session_state["reset_last_sent_email"] = None

        with col2:
            if st.button("Back"):
                st.session_state["reset_stage"] = "verify_code"
                st.rerun()

    cursor.close()
    conn.close()


# ---------------- LOGOUT ----------------
def logout(cookies):
    st.session_state["logged_in"] = False
    st.session_state["user_id"] = None
    st.session_state["username"] = None
    st.session_state["role"] = None
    st.session_state["page"] = "landing"
    st.session_state["tracks"] = []
    st.session_state["current_menu"] = None
    st.session_state["feed_view_mode"] = "all"
    st.session_state["show_followers_list"] = False
    st.session_state["show_following_list"] = False
    st.session_state["signup_otp_sent"] = False
    st.session_state["signup_pending"] = None
    st.session_state["reset_stage"] = "email"
    st.session_state["reset_otp_sent"] = False
    st.session_state["reset_pending_email"] = None
    st.session_state["reset_otp"] = None
    st.session_state["reset_otp_expiry"] = None
    st.session_state["reset_last_sent_email"] = None

    cookies["user_id"] = ""
    cookies["username"] = ""
    cookies["role"] = ""
    cookies["current_menu"] = ""
    cookies.save()
