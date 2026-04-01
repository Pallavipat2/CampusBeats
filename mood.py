import streamlit as st
import db 
import os
import pandas as pd
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
    current_role = st.session_state.get("role", "student")

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

        campus_group = user["campus_group"] if user["campus_group"] else ""
        year = user["year_of_study"] if user["year_of_study"] else ""

        if current_role != "admin":
            campus_group = st.text_input(
                "Campus Group / Department",
                value=campus_group
            )

            year_options = ["1st Year","2nd Year","3rd Year","4th Year","Postgrad"]
            year_index = year_options.index(year) if year in year_options else 0
            year = st.selectbox(
                "Year of Study",
                year_options,
                index=year_index,
            )

    if st.button("Save Profile"):

        profile_path = user["profile_pic"]

        if uploaded_file:

            os.makedirs("profile_pics", exist_ok=True)

            file_path = f"profile_pics/{user_id}_{uploaded_file.name}"

            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            profile_path = file_path

        if current_role == "admin":
            cursor.execute("""
            UPDATE users
            SET bio=%s, profile_pic=%s
            WHERE id=%s
            """,(bio, profile_path, user_id))
        else:
            cursor.execute("""
            UPDATE users
            SET bio=%s, campus_group=%s, year_of_study=%s, profile_pic=%s
            WHERE id=%s
            """,(bio, campus_group, year, profile_path, user_id))

        conn.commit()

        st.success("Profile updated!")
        st.rerun()

    if current_role == "admin":
        return

    st.divider()

    st.subheader("Mood Dashboard")
    st.caption("A quick look at your mood patterns, favorite genres, and posting trends over time.")

    cursor.execute("""
        SELECT
            p.mood,
            COALESCE(s.genre, 'No genre') AS genre,
            DATE(p.created_at) AS entry_date
        FROM posts p
        LEFT JOIN songs s ON p.song_id = s.id
        WHERE p.user_id = %s
        ORDER BY p.created_at ASC
    """, (user_id,))
    entries = cursor.fetchall()

    if not entries:
        st.info("Create a few mood posts to unlock your dashboard insights.")
        return

    dashboard_df = pd.DataFrame(entries)
    dashboard_df["entry_date"] = pd.to_datetime(dashboard_df["entry_date"])

    mood_counts = (
        dashboard_df.groupby("mood")
        .size()
        .reset_index(name="posts")
        .sort_values("posts", ascending=False)
    )

    genre_counts = (
        dashboard_df.groupby("genre")
        .size()
        .reset_index(name="posts")
        .sort_values("posts", ascending=False)
    )

    posts_over_time = (
        dashboard_df.groupby("entry_date")
        .size()
        .reset_index(name="posts")
        .sort_values("entry_date")
        .set_index("entry_date")
    )

    mood_trends = (
        dashboard_df.groupby(["entry_date", "mood"])
        .size()
        .reset_index(name="posts")
        .pivot(index="entry_date", columns="mood", values="posts")
        .fillna(0)
        .sort_index()
    )

    dominant_mood = mood_counts.iloc[0]["mood"]
    dominant_genre = genre_counts.iloc[0]["genre"]
    total_posts = int(len(dashboard_df))

    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("Dominant Mood", dominant_mood)
    stat2.metric("Dominant Genre", dominant_genre)
    stat3.metric("Total Entries", total_posts)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**Mood Distribution**")
        st.bar_chart(mood_counts.set_index("mood"))

    with chart_col2:
        st.markdown("**Genre Distribution**")
        st.bar_chart(genre_counts.set_index("genre"))

    st.markdown("**Posting Trend Over Time**")
    st.line_chart(posts_over_time)

    if not mood_trends.empty:
        st.markdown("**Mood Trends Over Time**")
        st.area_chart(mood_trends)
    
    
    
