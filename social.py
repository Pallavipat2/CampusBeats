#create post
#feed display
#likes
#comments
import streamlit as st


# =====================================================
# =======================FEED =======================
# =====================================================
def show_feed(cursor, conn, current_user):

    cursor.execute("""
        SELECT 
            posts.*,
            users.username,
            songs.song_name,
            songs.artist_name,
            songs.album_name,
            songs.spotify_track_id,
            COUNT(likes.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN songs ON posts.song_id = songs.id
        LEFT JOIN likes ON posts.id = likes.post_id
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
        GROUP BY posts.id
        ORDER BY posts.created_at DESC
    """, (current_user, current_user))

    posts = cursor.fetchall()

    if not posts:
        st.info("No posts yet.")
        return

    for post in posts:

        post_id = post["id"]

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

        col1, col2 = st.columns(2)

        # ❤️ LIKE BUTTON
        with col1:

            cursor.execute("""
                SELECT id FROM likes
                WHERE user_id=%s AND post_id=%s
            """, (current_user, post_id))

            liked = cursor.fetchone()

            if liked:
                if st.button(f"💔 Unlike ({post['like_count']})", key=f"unlike_{post_id}"):

                    cursor.execute("""
                        DELETE FROM likes
                        WHERE user_id=%s AND post_id=%s
                    """, (current_user, post_id))

                    conn.commit()
                    st.rerun()

            else:
                if st.button(f"❤️ Like ({post['like_count']})", key=f"like_{post_id}"):

                    cursor.execute("""
                        INSERT INTO likes (user_id, post_id)
                        VALUES (%s,%s)
                    """, (current_user, post_id))

                    conn.commit()
                    st.rerun()


        # 💬 COMMENTS
        with col2:
            st.write("💬 Comments")

            cursor.execute("""
                SELECT comments.comment_text, users.username
                FROM comments
                JOIN users ON comments.user_id = users.id
                WHERE comments.post_id=%s
                ORDER BY comments.created_at DESC
            """, (post_id,))

            comments = cursor.fetchall()

            for comment in comments:
                st.write(f"**{comment['username']}**: {comment['comment_text']}")

            new_comment = st.text_input(
                "Write a comment",
                key=f"comment_input_{post_id}"
            )

            if st.button("Post", key=f"comment_btn_{post_id}"):

                if new_comment.strip():

                    cursor.execute("""
                        INSERT INTO comments (user_id, post_id, comment_text)
                        VALUES (%s,%s,%s)
                    """, (current_user, post_id, new_comment))

                    conn.commit()
                    st.rerun()

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
 