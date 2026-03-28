import streamlit as st
import db 
import os
import streamlit.components.v1 as components

#=====================================================
# ================= GENRE MAP =================
GENRE_MAP = {
    "Pop": ["pop", "k-pop"],
    "Rock": ["rock", "metal", "punk"],
    "Hip-Hop": ["hip hop", "rap", "trap"],
    "Electronic": ["edm", "electronic", "house", "techno"],
    "Indie": ["indie", "indie pop", "indie rock"],
    "Classical": ["classical", "instrumental"],
    "Jazz": ["jazz", "blues"],
    "Lo-fi": ["lofi", "chillhop"],
    "Indian": ["bollywood", "desi", "tollywood", "kollywood"],
}

# ================= GENRE CLASSIFIER =================
def classify_genre(genres):
    if not genres:
        return "Unknown"

    genres_lower = [g.lower() for g in genres]

    for category, keywords in GENRE_MAP.items():
        for g in genres_lower:
            if any(keyword in g for keyword in keywords):
                return category

    return genres[0].title()




# =====================================================
# ==================== MOOD LOGGER =====================
# =====================================================
def show_mood_logger(cursor, conn, sp):

    st.title("🎵 Mood Music Journal")

    query = st.text_input("Search for a song")

    if st.button("Search"):
        if query:
            results = sp.search(q=query, type="track", limit=5)
            st.session_state["tracks"] = results['tracks']['items']

    tracks = st.session_state.get("tracks", [])

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
        genres = artist_info.get('genres', [])
        genre_category = classify_genre(genres)

        embed_url = f"https://open.spotify.com/embed/track/{spotify_track_id}"

        st.write("Selected:", song_name, "-", artist_name)
        st.write("Album:", album_name)

        components.iframe(embed_url, height=80)

        if track['album']['images']:
            st.image(track['album']['images'][0]['url'], width=200)

        mood = st.selectbox(
            "Choose your mood",
            [
                "Happy","Sad","Stressed","Excited","Overthinking","Content",
                "Calm","Hopeful","Proud","Grateful","Inspired","Lonely",
                "Tired","Disappointed","Anxious","Overwhelmed","Motivated",
                "Hopeless","Enraged","Lost","Nostalgic"
            ]
        )

        journal = st.text_area("Journal")

        visibility = st.selectbox(
            "Who can see this post?",
            ["private", "followers", "public"]
        )

        if st.button("Post Entry"):

            user_id = st.session_state["user_id"]

            # Insert song if not already stored
            cursor.execute("""
                INSERT IGNORE INTO songs
                (spotify_track_id, song_name, artist_name, album_name, genre)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                spotify_track_id,
                song_name,
                artist_name,
                album_name,
                genre_category
            ))
            conn.commit()

            # Retrieve song ID
            cursor.execute("""
                SELECT id FROM songs
                WHERE spotify_track_id=%s
            """, (spotify_track_id,))

            result = cursor.fetchone()

            if result is None:
                st.error("Song could not be saved.")
                st.stop()

            song_id = result["id"]

            # Insert post
            cursor.execute("""
                INSERT INTO posts
                (user_id, song_id, mood, journal_text, visibility)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user_id,
                song_id,
                mood,
                journal,
                visibility
            ))

            conn.commit()

            st.success("Post created successfully!")

# =====================================================
# ===================== Profile======================
# =====================================================
def show_profile_page(cursor, conn):

    st.title("👤 My Profile")

    user_id = st.session_state["user_id"]

    cursor.execute("SELECT * FROM users WHERE id=%s",(user_id,))
    user = cursor.fetchone()

    col1, col2 = st.columns([1,3])

    # PROFILE PIC
    with col1:
        if user["profile_pic"]:
            st.image(user["profile_pic"], width=150)
        else:
            st.image(
                "https://cdn-icons-png.flaticon.com/512/149/149071.png",
                width=150
            )

        uploaded_file = st.file_uploader("Upload profile picture", type=["png","jpg","jpeg"])

    # PROFILE INFO
    with col2:

        st.subheader(user["username"])

        bio = st.text_area(
            "Bio",
            value=user["bio"] if user["bio"] else ""
        )

        campus_group = st.text_input(
            "Campus Group / Department",
            value=user["campus_group"] if user["campus_group"] else ""
        )

        year = st.selectbox(
            "Year of Study",
            ["1st Year","2nd Year","3rd Year","4th Year","Postgrad"],
        )

    if st.button("Save Profile"):

        profile_path = user["profile_pic"]

        if uploaded_file:

            os.makedirs("profile_pics", exist_ok=True)

            file_path = f"profile_pics/{user_id}_{uploaded_file.name}"

            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            profile_path = file_path

        cursor.execute("""
        UPDATE users
        SET bio=%s, campus_group=%s, year_of_study=%s, profile_pic=%s
        WHERE id=%s
        """,(bio, campus_group, year, profile_path, user_id))

        conn.commit()

        st.success("Profile updated!")
        st.rerun()

    st.divider()
    
    
    
