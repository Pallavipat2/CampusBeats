#create post
#feed display
#likes
#comments
import streamlit as st


# =====================================================
# =======================FEED =======================
# =====================================================
def show_feed(cursor, current_user):

    cursor.execute("""
        SELECT 
            posts.*,
            users.username,
            songs.song_name,
            songs.artist_name,
            songs.album_name,
            songs.spotify_track_id
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN songs ON posts.song_id = songs.id
        WHERE
            posts.user_id = %s
            OR posts.visibility = 'public'
            OR (
                posts.visibility = 'followers'
                AND posts.user_id IN (
                    SELECT following_id
                    FROM follows
                    WHERE follower_id = %s
                )
            )
        ORDER BY posts.created_at DESC
    """, (current_user, current_user))

    posts = cursor.fetchall()

    if not posts:
        st.info("No posts yet.")
        return

    for post in posts:

        st.subheader(post["username"])

        if post["song_name"]:
            st.write("🎵 Song:", post["song_name"], "-", post["artist_name"])

            spotify_url = f"https://open.spotify.com/embed/track/{post['spotify_track_id']}"

            st.components.v1.iframe(
                spotify_url,
                height=80
            )

        st.write("Mood:", post["mood"])
        st.write(post["journal_text"])
        st.caption(post["created_at"])

        st.divider()


# =====================================================
# ====================Follow user =====================
# =====================================================
def follow_user(cursor, connection, current_user, target_user):

    cursor.execute("""
        INSERT INTO follows (follower_id, following_id)
        VALUES (%s, %s)
    """, (current_user, target_user))

    connection.commit()

    st.success("You are now following this user")
    
    
# =====================================================
# ====================Unfollow user =====================       
# =====================================================
def unfollow_user(cursor, connection, current_user, target_user):

    cursor.execute("""
        DELETE FROM follows
        WHERE follower_id=%s AND following_id=%s
    """, (current_user, target_user))

    connection.commit()

    st.success("You have unfollowed this user")
    
    
# =====================================================
# ==================Discovering users =================
# =====================================================
def discover_users(cursor, conn):

    st.title("Discover People")

    current_user = st.session_state["user_id"]

    cursor.execute("SELECT id, username FROM users")
    users = cursor.fetchall()

    for user in users:

        if user["id"] != current_user:

            st.write(user["username"])

            # Check if already following
            cursor.execute("""
                SELECT * FROM follows
                WHERE follower_id=%s AND following_id=%s
            """, (current_user, user["id"]))

            already_following = cursor.fetchone()

            if already_following:

                if st.button(f"Unfollow {user['username']}", key=f"u{user['id']}"):
                    unfollow_user(cursor, conn, current_user, user["id"])

            else:

                if st.button(f"Follow {user['username']}", key=f"f{user['id']}"):
                    follow_user(cursor, conn, current_user, user["id"])
 