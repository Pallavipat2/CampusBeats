import os
import streamlit as st
import streamlit.components.v1 as components
from Auth import (
    forgot_password_page,
    init_auth_session,
    login_page,
    maybe_route_password_reset,
    logout,
    reset_password_page,
    restore_supabase_session,
    signup_page,
    sync_auth_redirect_from_url,
)
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

st.set_page_config(page_title="Campus Beats", layout="wide")

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

params = st.query_params

if (
    params.get("type") == "recovery"
    or (params.get("access_token") and params.get("refresh_token"))
    or params.get("token_hash")
    or params.get("code")
):
    from Auth import reset_password_page
    reset_password_page(None)
    st.stop()


from db import get_supabase_client
from mood import show_mood_logger, show_profile_page
import social
from admin import admin_dashboard
from streamlit_cookies_manager import EncryptedCookieManager

# ================= COOKIES =================
cookies = EncryptedCookieManager(
    prefix="campus_beats",
    password="campus_beats_secret_123"
)

if not cookies.ready():
    st.stop()

# ================= DATABASE =================
try:
    supabase = get_supabase_client()
except Exception as e:
    st.error(f"Supabase connection failed: {e}")
    st.stop()

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

@keyframes cb-float {
    0% { transform: translateY(0px); }
    50% { transform: translateY(-8px); }
    100% { transform: translateY(0px); }
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

.cb-landing-hero {
    position: relative;
    overflow: hidden;
    background:
        radial-gradient(circle at 18% 24%, rgba(155, 200, 112, 0.36), transparent 24%),
        radial-gradient(circle at 82% 18%, rgba(148, 205, 216, 0.34), transparent 26%),
        linear-gradient(140deg, rgba(255,255,255,0.88), rgba(230,244,238,0.88));
    border: 1px solid rgba(107, 181, 166, 0.28);
    border-radius: 28px;
    padding: 1.6rem 1.6rem 1.2rem 1.6rem;
    box-shadow: 0 18px 40px rgba(52, 93, 83, 0.12);
    margin-bottom: 1rem;
}

.cb-landing-hero::after {
    content: "";
    position: absolute;
    inset: auto -10% -30% auto;
    width: 220px;
    height: 220px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(107,181,166,0.2), transparent 70%);
    animation: cb-float 5s ease-in-out infinite;
}

.cb-kicker {
    display: inline-block;
    padding: .32rem .78rem;
    border-radius: 999px;
    background: rgba(24, 68, 61, 0.08);
    color: #21584e;
    font-size: .82rem;
    font-weight: 700;
    letter-spacing: .02em;
    margin-bottom: .8rem;
}

.cb-hero-title {
    font-size: clamp(2rem, 4vw, 3.6rem);
    line-height: .98;
    margin: 0;
    color: #123d36;
}

.cb-hero-copy {
    margin: .9rem 0 1.1rem 0;
    font-size: 1.02rem;
    color: #2e5d55;
    max-width: 36rem;
}

.cb-mini-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: .8rem;
    margin-top: .8rem;
}

.cb-stat {
    background: rgba(255,255,255,0.72);
    border: 1px solid rgba(107, 181, 166, 0.18);
    border-radius: 18px;
    padding: .9rem 1rem;
}

.cb-stat strong {
    display: block;
    font-size: 1.2rem;
    color: #18443d;
}

.cb-stat span {
    color: #497268;
    font-size: .86rem;
}

.cb-feature-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: .9rem;
    margin-top: 1rem;
}

.cb-feature-card {
    background: rgba(255,255,255,0.82);
    border: 1px solid rgba(107, 181, 166, 0.18);
    border-radius: 20px;
    padding: 1rem;
    min-height: 150px;
    box-shadow: 0 10px 24px rgba(0,0,0,0.05);
}

.cb-feature-card h4 {
    margin: 0 0 .45rem 0;
    color: #17453d;
}

.cb-feature-card p {
    margin: 0;
    color: #466a63;
    font-size: .93rem;
}

.cb-vibe-panel {
    background: linear-gradient(135deg, rgba(24,68,61,0.95), rgba(107,181,166,0.92));
    color: white;
    border-radius: 24px;
    padding: 1.2rem;
    box-shadow: 0 16px 30px rgba(24,68,61,0.18);
}

.cb-vibe-panel h4 {
    margin: 0 0 .35rem 0;
    color: white;
}

.cb-vibe-panel p {
    margin: 0;
    color: rgba(255,255,255,0.86);
    font-size: .92rem;
}

.cb-vibe-badge {
    display: inline-block;
    margin-top: .9rem;
    padding: .42rem .9rem;
    background: rgba(255,255,255,0.18);
    border: 1px solid rgba(255,255,255,0.22);
    border-radius: 999px;
    font-weight: 700;
}

.cb-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    background: rgba(255,255,255,0.7);
    border: 1px solid rgba(107, 181, 166, 0.2);
    border-radius: 22px;
    padding: .85rem 1rem;
    margin-bottom: 1rem;
    backdrop-filter: blur(8px);
    box-shadow: 0 10px 24px rgba(30, 74, 66, 0.08);
}

.cb-brand {
    display: flex;
    flex-direction: column;
}

.cb-brand strong {
    color: #123d36;
    font-size: 1.05rem;
}

.cb-brand span {
    color: #4d736a;
    font-size: .86rem;
}

@media (max-width: 900px) {
    .cb-mini-stats,
    .cb-feature-grid {
        grid-template-columns: 1fr;
    }
}
</style>
""", unsafe_allow_html=True)

# ================= SESSION =================
init_auth_session()
sync_auth_redirect_from_url()
maybe_route_password_reset()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "page" not in st.session_state:
    st.session_state["page"] = "landing"

if "tracks" not in st.session_state:
    st.session_state["tracks"] = []

if "current_menu" not in st.session_state:
    st.session_state["current_menu"] = None

# ================= RESTORE LOGIN =================
if not st.session_state["logged_in"]:
    restored = restore_supabase_session(cookies)
    if restored:
        st.session_state["current_menu"] = cookies.get("current_menu")

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
    if "landing_vibe" not in st.session_state:
        st.session_state["landing_vibe"] = "Late-night Lo-fi"

    vibe_options = [
        "Late-night Lo-fi",
        "Campus Pop Rush",
        "Indie Rain Walk",
        "Exam Survival Mode",
        "Festival Energy",
    ]

    vibe_copy = {
        "Late-night Lo-fi": "Soft beats, reflective moods, and journal entries that feel like a midnight window seat.",
        "Campus Pop Rush": "Bright hooks, quick uploads, and a feed full of everyday campus main-character moments.",
        "Indie Rain Walk": "Gentle chaos, cloudy skies, and songs that feel handwritten in the margins.",
        "Exam Survival Mode": "Focus playlists, stress check-ins, and music that carries you through deadline season.",
        "Festival Energy": "Big emotions, louder tracks, and posts that feel like the whole campus is awake at once.",
    }

    nav_col1, nav_col2 = st.columns([3.4, 1.4], gap="medium")

    with nav_col1:
        st.markdown("""
        <div class="cb-topbar">
            <div class="cb-brand">
                <strong>Campus Beats</strong>
                <span>Your campus soundtrack, mood by mood.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with nav_col2:
        nav_btn1, nav_btn2 = st.columns(2, gap="small")
        with nav_btn1:
            if st.button("Login", use_container_width=True, key="landing_nav_login"):
                st.session_state["page"] = "login"
                st.rerun()
        with nav_btn2:
            if st.button("Signup", use_container_width=True, key="landing_nav_signup"):
                st.session_state["page"] = "signup"
                st.rerun()

    hero_col, vibe_col = st.columns([1.7, 1], gap="large")

    with hero_col:
        st.markdown("""
        <div class="cb-landing-hero">
            <div class="cb-kicker">Mood journal + social soundtrack</div>
            <h1 class="cb-hero-title">Campus Beats</h1>
            <p class="cb-hero-copy">
                Discover songs that match your mood, turn daily feelings into music memories,
                and share the soundtrack of campus life with people who get it.
            </p>
            <div class="cb-mini-stats">
                <div class="cb-stat"><strong>Track moods</strong><span>Turn feelings into music-backed entries.</span></div>
                <div class="cb-stat"><strong>Share moments</strong><span>Post songs, captions, videos, and campus updates.</span></div>
                <div class="cb-stat"><strong>Find your circle</strong><span>Follow classmates and explore shared vibes.</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with vibe_col:
        st.markdown('<div class="cb-vibe-panel">', unsafe_allow_html=True)
        st.markdown("<h4>Pick today's vibe</h4><p>Tap through a few moods and see what Campus Beats could feel like right now.</p>", unsafe_allow_html=True)
        selected_vibe = st.select_slider(
            "Today's vibe",
            options=vibe_options,
            value=st.session_state["landing_vibe"],
            label_visibility="collapsed",
        )
        st.session_state["landing_vibe"] = selected_vibe
        st.markdown(f'<div class="cb-vibe-badge">{selected_vibe}</div>', unsafe_allow_html=True)
        st.caption(vibe_copy[selected_vibe])
        st.markdown("</div>", unsafe_allow_html=True)

    st.image("banner.png", use_container_width=True)

    st.markdown("""
    <div class="cb-feature-grid">
        <div class="cb-feature-card">
            <h4>Journal with music</h4>
            <p>Log how you feel, save the song that matched that moment, and build a story of your semester through sound.</p>
        </div>
        <div class="cb-feature-card">
            <h4>See mood patterns</h4>
            <p>Use your profile dashboard to spot dominant moods, favorite genres, and how your listening changes over time.</p>
        </div>
        <div class="cb-feature-card">
            <h4>Share campus energy</h4>
            <p>Post videos, connect with classmates, and keep up with announcements and the emotional pulse of your campus.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.info("Start by choosing a vibe, then jump in and build your campus soundtrack.")

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
        signup_page(cookies)

        if st.button("⬅ Back"):
            st.session_state["page"] = "landing"
            st.rerun()

    elif st.session_state["page"] == "forgot":
        forgot_password_page()

        if st.button("⬅ Back"):
            st.session_state["page"] = "landing"
            st.rerun()

    elif st.session_state["page"] == "reset_password":
        reset_password_page(cookies)

        if st.button("Back", key="reset_password_back"):
            st.session_state["page"] = "login"
            st.rerun()

# ---------- LOGGED IN ----------
else:
    role = st.session_state.get("role")

    if role == "admin":
        menu_options = ["Admin Dashboard", "Profile", "Feed", "Discover People"]
    else:
        menu_options = ["Mood Logger", "My Mood Posts", "Profile", "Feed", "Discover People"]

    saved_menu = st.session_state.get("current_menu") or cookies.get("current_menu")
    if saved_menu not in menu_options:
        saved_menu = menu_options[0]

    if st.session_state.get("current_menu") not in menu_options:
        st.session_state["current_menu"] = saved_menu

    if role == "admin":
        menu = st.sidebar.selectbox(
            "Menu",
            menu_options,
            index=menu_options.index(st.session_state["current_menu"]),
            key="current_menu",
        )
        st.sidebar.success(f"Admin: {st.session_state['username']}")
    else:
        menu = st.sidebar.selectbox(
            "Menu",
            menu_options,
            index=menu_options.index(st.session_state["current_menu"]),
            key="current_menu",
        )
        st.sidebar.success(st.session_state["username"])

    if menu != cookies.get("current_menu"):
        cookies["current_menu"] = menu
        cookies.save()

    top_spacer, top_logout = st.columns([6, 1])
    with top_spacer:
        st.empty()
    with top_logout:
        if st.button("Logout", use_container_width=True, key="top_logout_button"):
            logout(cookies)
            st.session_state["page"] = "landing"
            st.session_state["tracks"] = []
            st.success("Logged out successfully!")
            st.rerun()

    # ---------- PAGES ----------
    if menu == "Admin Dashboard":
        admin_dashboard(supabase)

    elif menu == "Mood Logger":
        show_mood_logger(supabase, sp)

    elif menu == "My Mood Posts":
        social.show_my_mood_posts(supabase, st.session_state["user_id"])

    elif menu == "Profile":
        show_profile_page(supabase)

    elif menu == "Feed":
        current_user = st.session_state["user_id"]

        st.title("Campus Beats Feed")

        with st.expander("Upload a music video"):
            social.show_video_upload(supabase, current_user)

        social.show_feed(supabase, current_user)

    elif menu == "Discover People":
        social.discover_users(supabase)
