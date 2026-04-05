import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from db import first_row, result_data


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


def classify_genre(genres):
    if not genres:
        return "Unknown"

    genres_lower = [g.lower() for g in genres]

    for category, keywords in GENRE_MAP.items():
        for g in genres_lower:
            if any(keyword in g for keyword in keywords):
                return category

    return genres[0].title()


def _profile_pic_public_url(storage_response):
    if isinstance(storage_response, str):
        return storage_response
    if isinstance(storage_response, dict):
        return storage_response.get("publicUrl") or storage_response.get("public_url")
    for attr in ("publicUrl", "public_url"):
        value = getattr(storage_response, attr, None)
        if value:
            return value
    return None


def _profile_pic_display_src(profile_pic):
    if not profile_pic:
        return "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    profile_pic = str(profile_pic)
    if profile_pic.startswith(("http://", "https://", "data:")):
        return profile_pic

    return "https://cdn-icons-png.flaticon.com/512/149/149071.png"


def _upload_profile_picture(supabase, user_id, uploaded_file):
    file_ext = uploaded_file.name.split(".")[-1].lower()
    file_name = f"{user_id}.{file_ext}"
    file_bytes = uploaded_file.getvalue()

    supabase.storage.from_("profile-pics").upload(
        path=file_name,
        file=file_bytes,
        file_options={
            "content-type": uploaded_file.type or f"image/{file_ext}",
            "upsert": "true",
        },
    )

    public_url = _profile_pic_public_url(
        supabase.storage.from_("profile-pics").get_public_url(file_name)
    )
    if not public_url:
        raise ValueError("Could not resolve the uploaded profile picture URL.")
    return public_url


def show_mood_logger(supabase, sp, spotify_error=None):
    st.title("Music Mood Journal")

    if sp is None:
        st.error(spotify_error or "Spotify search is unavailable right now.")
        st.info("Add valid Spotify API credentials to enable song search in Mood Logger.")
        return

    query = st.text_input("Search for a song")

    if st.button("Search"):
        if query:
            try:
                results = sp.search(q=query, type="track", limit=5)
                st.session_state["tracks"] = results["tracks"]["items"]
            except Exception as error:
                st.error(f"Spotify search failed: {error}")
                return

    tracks = st.session_state.get("tracks", [])

    if not tracks:
        return

    song_options = [
        f"{track['name']} - {track['artists'][0]['name']}"
        for track in tracks
    ]

    selected_song = st.selectbox("Select a song", song_options)
    selected_index = song_options.index(selected_song)
    track = tracks[selected_index]

    spotify_track_id = track["id"]
    song_name = track["name"]
    artist_name = track["artists"][0]["name"]
    album_name = track["album"]["name"]
    artist_id = track["artists"][0]["id"]

    artist_info = sp.artist(artist_id)
    genres = artist_info.get("genres", [])
    genre_category = classify_genre(genres)

    embed_url = f"https://open.spotify.com/embed/track/{spotify_track_id}"

    st.write("Selected:", song_name, "-", artist_name)
    st.write("Album:", album_name)

    components.iframe(embed_url, height=80)

    if track["album"]["images"]:
        st.image(track["album"]["images"][0]["url"], width=200)

    mood = st.selectbox(
        "Choose your mood",
        [
            "Happy", "Sad", "Stressed", "Excited", "Overthinking", "Content",
            "Calm", "Hopeful", "Proud", "Grateful", "Inspired", "Lonely",
            "Tired", "Disappointed", "Anxious", "Overwhelmed", "Motivated",
            "Hopeless", "Enraged", "Lost", "Nostalgic",
        ],
    )

    journal = st.text_area("Journal")
    visibility = st.selectbox(
        "Who can see this post?",
        ["private", "followers", "public"],
    )

    if st.button("Post Entry"):
        user_id = st.session_state["user_id"]
        song_row = first_row(
            supabase.table("songs")
            .select("id")
            .eq("spotify_track_id", spotify_track_id)
            .limit(1)
            .execute()
        )

        if song_row is None:
            try:
                supabase.table("songs").upsert(
                    {
                        "spotify_track_id": spotify_track_id,
                        "song_name": song_name,
                        "artist_name": artist_name,
                        "album_name": album_name,
                        "genre": genre_category,
                    },
                    on_conflict="spotify_track_id",
                ).execute()
            except Exception as error:
                if 'row-level security policy for table "songs"' in str(error):
                    st.error(
                        "Supabase is blocking writes to `public.songs`. "
                        "Please re-run the `songs` RLS section in "
                        "`supabase_public_users_migration.sql`, then try posting again."
                    )
                    return
                raise

            song_row = first_row(
                supabase.table("songs")
                .select("id")
                .eq("spotify_track_id", spotify_track_id)
                .limit(1)
                .execute()
            )

        if song_row is None:
            st.error("Song could not be saved.")
            return

        supabase.table("posts").insert(
            {
                "user_id": user_id,
                "song_id": song_row["id"],
                "mood": mood,
                "journal_text": journal,
                "visibility": visibility,
            }
        ).execute()

        st.success("Post created successfully!")


def show_profile_page(supabase):
    st.title("My Profile")

    user_id = st.session_state["user_id"]
    current_role = st.session_state.get("role", "student")

    user = first_row(
        supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    )

    if not user:
        st.error("Could not load your profile.")
        return

    col1, col2 = st.columns([1, 3])

    with col1:
        st.image(_profile_pic_display_src(user.get("profile_pic")), width=150)

        uploaded_file = st.file_uploader("Upload profile picture", type=["png", "jpg", "jpeg"])

    with col2:
        st.subheader(user["username"])

        bio = st.text_area("Bio", value=user.get("bio") or "")
        campus_group = user.get("campus_group") or ""
        year = user.get("year_of_study") or ""

        if current_role != "admin":
            campus_group = st.text_input("Campus Group / Department", value=campus_group)

            year_options = ["1st Year", "2nd Year", "3rd Year", "4th Year", "Postgrad"]
            year_index = year_options.index(year) if year in year_options else 0
            year = st.selectbox("Year of Study", year_options, index=year_index)

    if st.button("Save Profile"):
        profile_path = user.get("profile_pic")

        if uploaded_file:
            try:
                profile_path = _upload_profile_picture(supabase, user_id, uploaded_file)
            except Exception as error:
                st.error(f"Profile picture upload failed: {error}")
                return

        payload = {"bio": bio, "profile_pic": profile_path}
        if current_role != "admin":
            payload["campus_group"] = campus_group
            payload["year_of_study"] = year

        try:
            supabase.table("users").update(payload).eq("id", user_id).execute()
        except Exception as error:
            if "column users." in str(error):
                st.error(
                    "Your `public.users` table is missing one or more profile columns. "
                    "Please re-run `supabase_public_users_migration.sql`, then try again."
                )
                return
            if 'row-level security policy for table "users"' in str(error):
                st.error(
                    "Supabase is blocking profile updates on `public.users`. "
                    "Please re-run the users RLS section in `supabase_public_users_migration.sql`."
                )
                return
            st.error(f"Profile update failed: {error}")
            return

        st.success("Profile updated!")
        st.rerun()

    if current_role == "admin":
        return

    st.divider()
    st.subheader("Mood Dashboard")
    st.caption("A quick look at your mood patterns, favorite genres, and posting trends over time.")

    posts = result_data(
        supabase.table("posts")
        .select("mood, created_at, song_id")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )

    if not posts:
        st.info("Create a few mood posts to unlock your dashboard insights.")
        return

    song_ids = sorted({post["song_id"] for post in posts if post.get("song_id") is not None})
    songs_by_id = {}
    if song_ids:
        songs = result_data(
            supabase.table("songs").select("id, genre").in_("id", song_ids).execute()
        )
        songs_by_id = {song["id"]: song for song in songs}

    entries = []
    for post in posts:
        created_at = post.get("created_at")
        entry_date = created_at[:10] if isinstance(created_at, str) else created_at
        song = songs_by_id.get(post.get("song_id"))
        entries.append(
            {
                "mood": post.get("mood"),
                "genre": (song or {}).get("genre") or "No genre",
                "entry_date": entry_date,
            }
        )

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
