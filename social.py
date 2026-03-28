# ================= IMPORTS =================
import streamlit as st
import os
import uuid

# ================= CONSTANTS =================
DEFAULT_PROFILE_PIC = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
UPLOAD_FOLDER = "uploads/videos"


# =====================================================
# ================= VIDEO UPLOAD ======================
# =====================================================
def show_video_upload(cursor, conn, current_user):
    st.subheader("📹 Upload Music Video")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    caption = st.text_area("Caption", key="video_caption")

    mood = st.selectbox(
        "Choose your mood",
        ["Happy","Sad","Stressed","Excited","Overthinking","Content",
         "Calm","Hopeful","Proud","Grateful","Inspired","Lonely",
         "Tired","Disappointed","Anxious","Overwhelmed","Motivated",
         "Hopeless","Enraged","Lost","Nostalgic"]
    )

    visibility = st.selectbox(
        "Visibility",
        ["public", "followers", "private"],
        key="video_visibility"
    )

    uploaded_video = st.file_uploader(
        "Upload a music video",
        type=["mp4", "mov", "avi", "mkv"],
        key="video_uploader"
    )

    if st.button("Post Video"):
        if uploaded_video is None:
            st.error("Please upload a video")
            return

        file_ext = uploaded_video.name.split(".")[-1]
        filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

        try:
            with open(file_path, "wb") as f:
                f.write(uploaded_video.read())

            cursor.execute("""
                INSERT INTO posts (user_id, song_id, mood, journal_text, visibility, video_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                current_user,
                None,
                mood,
                caption,
                visibility,
                file_path
            ))

            conn.commit()
            st.success("Video uploaded successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"Upload failed: {e}")


# =====================================================
# ======================= FEED =========================
# =====================================================
def show_feed(cursor, conn, current_user):
    import streamlit as st
    import os

    DEFAULT_PROFILE_PIC = "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    # 🔥 GLOBAL CSS (safe targeting)
    st.markdown("""
    <style>

    .post-card {
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    }

    .admin-post {
        background: linear-gradient(190deg, #FFE082, #FFC107);
        border: 2px solid #DAA520;
    }

    .announcement-post {
        background: linear-gradient(135deg, #CAD7A5, #6BB5A6);
        border: 2px solid #617F6A;
        box-shadow: 0 8px 25px rgba(207, 229, 213,0.4);
    }

    .normal-post {
        background: #ffffff;
        border: 1px solid #ddd;
    }

    </style>
    """, unsafe_allow_html=True)

    # ================= DB =================
    cursor.execute("""
        SELECT 
            posts.*,
            users.username,
            users.profile_pic,
            users.role,
            COUNT(likes.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN likes ON posts.id = likes.post_id
        WHERE
            posts.user_id = %s
            OR posts.visibility = 'public'
            OR (
                posts.visibility = 'followers'
                AND posts.user_id IN (
                    SELECT following_id FROM follows WHERE follower_id = %s
                )
            )
        GROUP BY posts.id
        ORDER BY
            CASE
                WHEN users.role = 'admin' AND posts.post_type = 'announcement' THEN 0
                WHEN users.role = 'admin' THEN 1
                ELSE 2
            END,
            posts.created_at DESC
    """, (current_user, current_user))

    posts = cursor.fetchall()

    if not posts:
        st.info("No posts yet.")
        return

    # ================= FEED =================
    for post in posts:

        role = post.get("role", "student")
        post_type = post.get("post_type", "music")
        post_id = post["id"]

        # 🎯 CLASS DECIDER
        if role == "admin" and post_type == "announcement":
            css_class = "post-card announcement-post"
        elif role == "admin":
            css_class = "post-card admin-post"
        else:
            css_class = "post-card normal-post"

        # 🔥 THIS is the trick: render EVERYTHING inside one markdown block
        content = f"""
        <div class="{css_class}">
            <b>{post['username']}</b>
            <br>
            <small>{post['created_at']}</small>
            <br><br>
            {post.get('caption', '')}
        </div>
        """

        st.markdown(content, unsafe_allow_html=True)

        # 👇 STREAMLIT ELEMENTS (kept after but visually grouped)
        if post.get("video_path") and os.path.exists(post["video_path"]):
            st.video(post["video_path"])

        # LIKE
        cursor.execute("SELECT id FROM likes WHERE user_id=%s AND post_id=%s",
                       (current_user, post_id))
        liked = cursor.fetchone()

        if liked:
            if st.button(f"💔 Unlike {post['like_count']}", key=f"u_{post_id}"):
                cursor.execute("DELETE FROM likes WHERE user_id=%s AND post_id=%s",
                               (current_user, post_id))
                conn.commit()
                st.rerun()
        else:
            if st.button(f"❤️ Like {post['like_count']}", key=f"l_{post_id}"):
                cursor.execute("INSERT INTO likes (user_id, post_id) VALUES (%s,%s)",
                               (current_user, post_id))
                conn.commit()
                st.rerun()

        st.divider()

# =====================================================
# ================= FOLLOW SYSTEM ======================
# =====================================================
def follow_user(cursor, conn, current_user, target_user):
    cursor.execute("""
        INSERT INTO follows (follower_id, following_id)
        VALUES (%s, %s)
    """, (current_user, target_user))
    conn.commit()
    st.success("Followed!")


def unfollow_user(cursor, conn, current_user, target_user):
    cursor.execute("""
        DELETE FROM follows
        WHERE follower_id=%s AND following_id=%s
    """, (current_user, target_user))
    conn.commit()
    st.success("Unfollowed!")


# =====================================================
# ================= DISCOVER USERS =====================
# =====================================================
def discover_users(cursor, conn):
    st.title("🔍 Discover People")

    current_user = st.session_state["user_id"]
    search = st.text_input("Search users")

    if search:
        cursor.execute("""
            SELECT id, username, bio, profile_pic
            FROM users
            WHERE username LIKE %s
        """, (f"%{search}%",))
    else:
        cursor.execute("SELECT id, username, bio, profile_pic FROM users")

    users = cursor.fetchall()

    for user in users:
        if user["id"] == current_user:
            continue

        cursor.execute("""
            SELECT * FROM follows
            WHERE follower_id=%s AND following_id=%s
        """, (current_user, user["id"]))

        following = cursor.fetchone()

        col1, col2, col3 = st.columns([1, 5, 2])

        with col1:
            st.image(user["profile_pic"] or DEFAULT_PROFILE_PIC, width=50)

        with col2:
            st.write(f"**{user['username']}**")
            if user["bio"]:
                st.caption(user["bio"])

        with col3:
            if following:
                if st.button("Unfollow", key=f"u{user['id']}"):
                    unfollow_user(cursor, conn, current_user, user["id"])
                    st.rerun()
            else:
                if st.button("Follow", key=f"f{user['id']}"):
                    follow_user(cursor, conn, current_user, user["id"])
                    st.rerun()

        st.divider()