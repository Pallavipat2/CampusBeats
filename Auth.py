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
    import streamlit as st

    defaults = {
        "signup_otp_sent": False,
        "signup_pending": None,
        "reset_otp_sent": False,
        "reset_pending_email": None,
        "logged_in": False,
        "user_id": None,
        "username": None,
        "role": None
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
                            "expiry": datetime.now() + timedelta(minutes=10)
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
                    """, (
                        pending["username"],
                        pending["email"],
                        hashed_pw,
                        1,
                        "student"
                    ))
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
    import streamlit as st
    from db import get_connection

    st.title("Login")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if st.button("Login"):
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if not user:
            st.error("User does not exist")

        elif not user["email_verified"]:
            st.error("Please verify your email before logging in")

        elif verify_password(password, user["password_hash"]):

            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user["id"]
            st.session_state["username"] = user["username"]
            st.session_state["role"] = user["role"]

            cookies["user_id"] = str(user["id"])
            cookies["username"] = user["username"]
            cookies["role"] = user["role"]
            cookies.save()

            st.success("Login successful!")
            st.rerun()

        else:
            st.error("Invalid credentials")

    cursor.close()
    conn.close()

# ---------------- FORGOT PASSWORD ----------------

def forgot_password_page():
    st.title("Forgot Password")

    email = st.text_input("Enter your registered email", key="forgot_email")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if not st.session_state["reset_otp_sent"]:
        if st.button("Send Reset Code"):
            if not email:
                st.error("Please enter your email")
            elif not valid_email(email):
                st.error("Enter a valid email address")
            else:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()

                if not user:
                    st.error("No account found with this email")
                else:
                    otp = generate_otp()
                    sent = send_email_otp(email, otp, purpose="reset")

                    if sent:
                        st.session_state["reset_pending_email"] = email
                        st.session_state["reset_otp"] = otp
                        st.session_state["reset_otp_expiry"] = datetime.now() + timedelta(minutes=10)
                        st.session_state["reset_otp_sent"] = True
                        st.success("Password reset code sent to your email")

    else:
        entered_otp = st.text_input("Enter Reset Code", key="reset_otp_input")
        new_password = st.text_input("New Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_password")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Reset Password"):
                if datetime.now() > st.session_state["reset_otp_expiry"]:
                    st.error("Reset code expired. Please request a new one.")
                    st.session_state["reset_otp_sent"] = False
                    st.session_state["reset_pending_email"] = None
                elif entered_otp != st.session_state["reset_otp"]:
                    st.error("Invalid reset code")
                elif not strong_password(new_password):
                    st.error("Password must be at least 8 characters long")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                else:
                    hashed_pw = hash_password(new_password)

                    cursor.execute("""
                        UPDATE users
                        SET password_hash = %s
                        WHERE email = %s
                    """, (hashed_pw, st.session_state["reset_pending_email"]))
                    conn.commit()

                    st.success("Password reset successfully! You can now log in.")
                    st.session_state["reset_otp_sent"] = False
                    st.session_state["reset_pending_email"] = None

        with col2:
            if st.button("Cancel Reset"):
                st.session_state["reset_otp_sent"] = False
                st.session_state["reset_pending_email"] = None
                st.rerun()

    cursor.close()
    conn.close()


# ---------------- LOGOUT ----------------
def logout(cookies):
    st.session_state["logged_in"] = False
    st.session_state["user_id"] = None
    st.session_state["username"] = None
    st.session_state["role"] = None

    cookies["user_id"] = ""
    cookies["username"] = ""
    cookies["role"] = ""
    cookies.save()