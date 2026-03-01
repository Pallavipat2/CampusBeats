import mysql.connector
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os
import bcrypt

# ================= LOAD ENV =================
load_dotenv()

MYSQLHOST = os.getenv("MYSQLHOST")
MYSQLUN = os.getenv("MYSQLUN")
MYSQLPW = os.getenv("MYSQLPW")
DATABASE = os.getenv("DATABASE")
CLIENTID = os.getenv("CLIENTID")
CLIENTSECRET = os.getenv("CLIENTSECRET")

# ================= SESSION STATE =================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "tracks" not in st.session_state:
    st.session_state["tracks"] = []

# ================= DATABASE CONNECTION =================
conn = mysql.connector.connect(
    host=MYSQLHOST,
    user=MYSQLUN,
    password=MYSQLPW,
    database=DATABASE
)
cursor = conn.cursor(dictionary=True)

# ================= PASSWORD FUNCTIONS =================
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ================= GENRE CLASSIFIER =================
def classify_genre(genres):
    genre_text = " ".join(genres).lower()
    if "k-pop" in genre_text:
        return "K-Pop"
    elif "indian classical" in genre_text:
        return "Indian Classical"
    elif "bollywood" in genre_text:
        return "Bollywood"
    elif "rock" in genre_text:
        return "Rock"
    else:
        return "Other"

# ================= SPOTIFY CONNECTION =================
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=CLIENTID,
    client_secret=CLIENTSECRET
))

# ================= SIDEBAR =================
if not st.session_state["logged_in"]:
    menu = st.sidebar.selectbox("Menu", ["Login", "Signup"])
else:
    menu = st.sidebar.selectbox("Menu", ["Mood Logger", "Dashboard", "Logout"])


# =====================================================
# ====================== SIGNUP ========================
# =====================================================
if menu == "Signup":

    st.title("Create Account")

    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Create Account"):

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            st.error("Username already exists")
        else:
            hashed_pw = hash_password(password)
            cursor.execute("""
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
            """, (username, email, hashed_pw))
            conn.commit()
            st.success("Account created successfully!")


# =====================================================
# ======================= LOGIN ========================
# =====================================================
elif menu == "Login":

    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()

        if user and verify_password(password, user['password_hash']):
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user["id"]
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid credentials")


# =====================================================
# ==================== MOOD LOGGER =====================
# =====================================================
elif menu == "Mood Logger":

    st.title("🎵 Mood Music Journal")

    query = st.text_input("Search for a song")

    if st.button("Search"):
        if query:
            results = sp.search(q=query, type="track", limit=5)
            st.session_state["tracks"] = results['tracks']['items']

    tracks = st.session_state["tracks"]

    if tracks:
        song_options = [
            f"{track['name']} - {track['artists'][0]['name']}"
            for track in tracks
        ]

        selected_song = st.selectbox("Select a song", song_options)
        selected_index = song_options.index(selected_song)
        track = tracks[selected_index]

        spotify_track_id = track['id']
        song_name = track['name']
        artist_name = track['artists'][0]['name']
        album_name = track['album']['name']
        artist_id = track['artists'][0]['id']

        artist_info = sp.artist(artist_id)
        genres = artist_info.get('genres',[])
        genre_category = classify_genre(genres)

        embed_url = f"https://open.spotify.com/embed/track/{spotify_track_id}"

        st.write("Selected:", song_name, "-", artist_name)
        st.write("Album:", album_name)
        components.iframe(embed_url, height=80)

        if track['album']['images']:
            st.image(track['album']['images'][0]['url'], width=200)

        mood = st.selectbox("Choose your mood",
                            ["Happy", "Sad", "Calm", "Anxious", "Excited"])
        journal = st.text_area("Journal")

        if st.button("Save Entry"):

            user_id = st.session_state["user_id"]

            # Insert song
            cursor.execute("""
                INSERT IGNORE INTO songs
                (spotify_track_id, song_name, artist_name, album_name, genre)
                VALUES (%s, %s, %s, %s, %s)
            """, (spotify_track_id, song_name,
                  artist_name, album_name, genre_category))
            conn.commit()

            # Get song ID
            cursor.execute("""
                SELECT id FROM songs
                WHERE spotify_track_id=%s
            """, (spotify_track_id,))
            result = cursor.fetchone()

            if not result:
                st.error("Song not found")
                st.stop()

            song_id = result['id']

            # Insert mood entry
            cursor.execute("""
                INSERT INTO mood_entries
                (user_id, song_id, mood, journal)
                VALUES (%s, %s, %s, %s)
            """, (user_id, song_id, mood, journal))
            conn.commit()

            st.success("Entry saved successfully!")


# =====================================================
# ===================== DASHBOARD ======================
# =====================================================
elif menu == "Dashboard":

    st.header("📊 Mood Analytics Dashboard")

    user_id = st.session_state["user_id"]

    cursor.execute("""
        SELECT mood, COUNT(*) as total
        FROM mood_entries
        WHERE user_id=%s
        GROUP BY mood
    """, (user_id,))
    mood_data = cursor.fetchall()

    if mood_data:

        moods = [row['mood'] for row in mood_data]
        counts = [row['total'] for row in mood_data]

        df = pd.DataFrame({"Mood": moods, "Songs": counts})

        cursor.execute("""
            SELECT COUNT(*) as total
            FROM mood_entries
            WHERE user_id=%s
        """, (user_id,))
        total_songs = cursor.fetchone()['total']

        cursor.execute("""
            SELECT mood, COUNT(*) as total
            FROM mood_entries
            WHERE user_id=%s
            GROUP BY mood
            ORDER BY total DESC
            LIMIT 1
        """, (user_id,))
        dominant_mood = cursor.fetchone()

        col1, col2 = st.columns(2)

        with col1:
            st.metric("🎵 Total Songs Logged", total_songs)

        with col2:
            if dominant_mood:
                st.metric("😌 Dominant Mood", dominant_mood['mood'])
            else:
                st.metric("😌 Dominant Mood", "No data")

        st.subheader("Mood Distribution")
        st.bar_chart(df.set_index("Mood"))

        st.subheader("Mood Breakdown")
        fig = df.set_index("Mood").plot.pie(
            y="Songs", autopct='%1.1f%%').figure
        st.pyplot(fig)

    else:
        st.info("No mood entries yet.")


# =====================================================
# ======================= LOGOUT =======================
# =====================================================
elif menu == "Logout":

    st.session_state["logged_in"] = False
    st.session_state["user_id"] = None
    st.session_state["tracks"] = []

    st.success("Logged out successfully!")
    st.rerun()


# ================= CLOSE CONNECTION =================
cursor.close()
conn.close()