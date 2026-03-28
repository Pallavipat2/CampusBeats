import os
import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from Auth import init_auth_session, login_page, signup_page, forgot_password_page, logout
from db import get_connection
from mood import show_mood_logger, show_profile_page
import social
from admin import admin_dashboard
from streamlit_cookies_manager import EncryptedCookieManager

st.set_page_config(page_title="Campus Beats", layout="wide")

# ================= COOKIES =================
cookies = EncryptedCookieManager(
    prefix="campus_beats",
    password="campus_beats_secret_123"
)

if not cookies.ready():
    st.stop()

# ================= DATABASE =================
conn = get_connection()
if conn is None:
    st.error("Database connection failed.")
    st.stop()

cursor = conn.cursor(dictionary=True)

# ================= CSS =================
st.markdown("""
<style>
:root {
    --cb-primary: #6bb5a6;
    --cb-secondary: #9bc870;
    --cb-accent: #cad7a5;
    --cb-surface: #c8e4d6;
    --cb-sky: #94cdd8;
    --cb-text: #18443d;
}

.stApp {
    background:
        radial-gradient(circle at 15% 20%, rgba(148, 205, 216, 0.32), transparent 28%),
        radial-gradient(circle at 85% 12%, rgba(155, 200, 112, 0.28), transparent 30%),
        linear-gradient(120deg, #f7fffb 0%, #eff8f4 100%);
    color: var(--cb-text);
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #c8e4d6 0%, #94cdd8 100%);
}

@keyframes cb-fade-up {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes cb-soft-pulse {
    0% { box-shadow: 0 0 0 0 rgba(107, 181, 166, 0.35); }
    70% { box-shadow: 0 0 0 14px rgba(107, 181, 166, 0); }
    100% { box-shadow: 0 0 0 0 rgba(107, 181, 166, 0); }
}

h1, h2, h3 {
    color: var(--cb-text);
    animation: cb-fade-up 0.5s ease both;
}

.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    border: 1px solid rgba(107, 181, 166, 0.45) !important;
    border-radius: 12px !important;
}

.stButton > button {
    border: none !important;
    border-radius: 12px !important;
    background: linear-gradient(135deg, var(--cb-primary), var(--cb-secondary)) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    transition: transform 0.22s ease, filter 0.22s ease !important;
    animation: cb-soft-pulse 2.8s infinite;
}

.stButton > button:hover {
    transform: translateY(-2px) scale(1.01);
    filter: brightness(1.07);
}

.cb-hero {
    background: linear-gradient(130deg, rgba(107, 181, 166, 0.14), rgba(200, 228, 214, 0.42));
    border: 1px solid rgba(107, 181, 166, 0.3);
    border-radius: 20px;
    padding: 1.1rem 1.2rem;
    margin-bottom: 1rem;
    animation: cb-fade-up 0.6s ease both;
}
img {
    border-radius: 50%;
    object-fit: cover;
}
</style>
""", unsafe_allow_html=True)

# ================= SESSION =================
init_auth_session()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "page" not in st.session_state:
    st.session_state["page"] = "landing"

if "tracks" not in st.session_state:
    st.session_state["tracks"] = []

# ================= RESTORE LOGIN =================
if not st.session_state["logged_in"]:
    user_id = cookies.get("user_id")

    if user_id:
        try:
            user_id = int(user_id)

            cursor.execute(
                "SELECT id, username, role FROM users WHERE id=%s",
                (user_id,)
            )
            user = cursor.fetchone()

            if user:
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = user["id"]
                st.session_state["username"] = user["username"]
                st.session_state["role"] = user["role"]
                st.session_state["page"] = "app"
            else:
                cookies["user_id"] = ""
                cookies.save()

        except:
            cookies["user_id"] = ""
            cookies.save()

# ================= SPOTIFY =================
CLIENTID = os.getenv("CLIENTID")
CLIENTSECRET = os.getenv("CLIENTSECRET")

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=CLIENTID,
        client_secret=CLIENTSECRET
    )
)

# ================= LANDING PAGE =================
def show_landing_page():
    st.markdown("""
    <div class="cb-hero">
      <h2 style="margin:0;">Campus Beats</h2>
      <p style="margin:.35rem 0 0 0;">Find your vibe, track your mood, and share your campus soundtrack.</p>
    </div>
    """, unsafe_allow_html=True)

    st.image("banner.png", use_container_width=True)

    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        if st.button("Login", use_container_width=True):
            st.session_state["page"] = "login"
            st.rerun()

        if st.button("Signup", use_container_width=True):
            st.session_state["page"] = "signup"
            st.rerun()

# ================= ROUTING =================

# ---------- NOT LOGGED IN ----------
if not st.session_state["logged_in"]:

    if st.session_state["page"] == "landing":
        show_landing_page()

    elif st.session_state["page"] == "login":
        login_page(cookies)

        if st.button("⬅ Back"):
            st.session_state["page"] = "landing"
            st.rerun()

    elif st.session_state["page"] == "signup":
        signup_page()

        if st.button("⬅ Back"):
            st.session_state["page"] = "landing"
            st.rerun()

    elif st.session_state["page"] == "forgot":
        forgot_password_page()

        if st.button("⬅ Back"):
            st.session_state["page"] = "landing"
            st.rerun()

# ---------- LOGGED IN ----------
else:
    role = st.session_state.get("role")

    if role == "admin":
        menu = st.sidebar.selectbox(
            "Menu",
              ["Admin Dashboard", "Mood Logger", "My Mood Posts", "Profile", "Feed", "Discover People", "Logout"]
        )
        st.sidebar.success(f"Admin: {st.session_state['username']}")
    else:
        menu = st.sidebar.selectbox(
            "Menu",
              ["Mood Logger", "My Mood Posts", "Profile", "Feed", "Discover People", "Logout"]
        )
        st.sidebar.success(st.session_state["username"])

    # ---------- PAGES ----------
    if menu == "Admin Dashboard":
        admin_dashboard(cursor, conn)

    elif menu == "Mood Logger":
        show_mood_logger(cursor, conn, sp)

    elif menu == "My Mood Posts":
        social.show_my_mood_posts(cursor, conn, st.session_state["user_id"])

    elif menu == "Profile":
        show_profile_page(cursor, conn)

    elif menu == "Feed":
        current_user = st.session_state["user_id"]

        st.title("Campus Beats Feed")

        with st.expander("Upload a music video"):
            social.show_video_upload(cursor, conn, current_user)

        social.show_feed(cursor, conn, current_user)

    elif menu == "Discover People":
        social.discover_users(cursor, conn)

    elif menu == "Logout":
        logout(cookies)
        st.session_state["page"] = "landing"
        st.session_state["tracks"] = []
        st.success("Logged out successfully!")
        st.rerun()

# ================= CLOSE =================
cursor.close()
conn.close()