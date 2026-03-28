# ================= IMPORTS =================
import streamlit as st
import os
import uuid

# ================= CONSTANTS =================
DEFAULT_PROFILE_PIC = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
UPLOAD_FOLDER = "uploads/videos"

def ensure_comments_table(cursor, conn):
    """Create comments table if it does not exist."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INT NOT NULL,
            user_id INT NOT NULL,
            comment_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()

def ensure_follow_requests_table(cursor, conn):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS follow_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            requester_id INT NOT NULL,
            recipient_id INT NOT NULL,
            status ENUM('pending','accepted','declined') NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_request_pair (requester_id, recipient_id)
        )
    """)
    conn.commit()

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
         "Hopeless","Enraged","Lost","Nostalgic",]
    )

    visibility = st.selectbox(
        "Visibility",
        ["public", "followers", "private"],
        key="video_visibility",
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

                cursor.execute(
                """
                INSERT INTO posts (user_id, song_id, mood, journal_text, visibility, video_path, caption)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (current_user, None, mood, caption, visibility, file_path, caption),
            )

            conn.commit()
            st.success("Video uploaded successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"Upload failed: {e}")

def can_view_post(post, current_user, following_ids):
    if post["user_id"] == current_user:
        return True
    if post["visibility"] == "public":
        return True
    if post["visibility"] == "followers" and post["user_id"] in following_ids:
        return True
    return False


def delete_post(cursor, conn, post_id):
    cursor.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    conn.commit()


def show_comments_section(cursor, conn, post_id, current_user):
    comments_key = f"show_comments_{post_id}"

    if comments_key not in st.session_state:
        st.session_state[comments_key] = False

    toggle_label = "Hide comments" if st.session_state[comments_key] else "Show comments"
    if st.button(toggle_label, key=f"toggle_comments_{post_id}"):
        st.session_state[comments_key] = not st.session_state[comments_key]
        st.rerun()

    if not st.session_state[comments_key]:
        return

    cursor.execute(
        """
        SELECT comments.comment_text, comments.created_at, users.username
        FROM comments
        JOIN users ON comments.user_id = users.id
        WHERE comments.post_id = %s
        ORDER BY comments.created_at ASC
        """,
        (post_id,),
    )
    comments = cursor.fetchall()

    if comments:
        for comment in comments:
            st.caption(f"**{comment['username']}** · {comment['created_at']}")
            st.write(comment["comment_text"])
    else:
        st.caption("No comments yet.")

    new_comment = st.text_input("Add a comment", key=f"comment_input_{post_id}")
    if st.button("Post Comment", key=f"comment_btn_{post_id}"):
        if not new_comment.strip():
            st.error("Comment cannot be empty")
            return

        cursor.execute(
            """
            INSERT INTO comments (post_id, user_id, comment_text)
            VALUES (%s, %s, %s)
            """,
            (post_id, current_user, new_comment.strip()),
        )
        conn.commit()
        st.success("Comment posted")
        st.rerun()

# =====================================================
# ======================= FEED =========================
# =====================================================
def show_feed(cursor, conn, current_user):
    ensure_comments_table(cursor, conn)

    st.markdown("""
    <style>
      @keyframes cb-card-in {
        from { opacity: 0; transform: translateY(10px) scale(0.99); }
        to { opacity: 1; transform: translateY(0) scale(1); }
    }

    @keyframes cb-shimmer {
        0% { background-position: -220px 0; }
        100% { background-position: 220px 0; }
    }
    .post-card {
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
         animation: cb-card-in 0.35s ease both;
        transition: transform .2s ease, box-shadow .2s ease;
    }

    .post-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.12);
    }

    .admin-post {
        background: linear-gradient(190deg, #FFE082, #FFC107);
        border: 2px solid #DAA520;
    }

    .announcement-post {
        background: linear-gradient(135deg, #CAD7A5, #6BB5A6);
        border: 2px solid #617F6A;
        box-shadow: 0 8px 25px rgba(207, 229, 213,0.4);
          position: relative;
        overflow: hidden;
    }

    .announcement-post::after {
        content: "";
        position: absolute;
        top: 0;
        left: -220px;
        width: 220px;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent);
        animation: cb-shimmer 3s linear infinite;
    }

    .normal-post {
      background: #ffffffd9;
        border: 1px solid #c8e4d6; background: #ffffffd9;
        border: 1px solid #c8e4d6;
    }

    </style>
    """, unsafe_allow_html=True,)
     
    cursor.execute("SELECT following_id FROM follows WHERE follower_id=%s", (current_user,))
    following_ids = {row["following_id"] for row in cursor.fetchall()}

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
        GROUP BY posts.id
        ORDER BY
            CASE
                WHEN users.role = 'admin' AND posts.post_type = 'announcement' THEN 0
                WHEN users.role = 'admin' THEN 1
                ELSE 2
            END,
            posts.created_at DESC
    """)

    posts = [p for p in cursor.fetchall() if can_view_post(p, current_user, following_ids)]

    if not posts:
        st.info("No posts yet.")
        return

    # ================= FEED =================
    current_role = st.session_state.get("role", "student")

    for post in posts:

        role = post.get("role", "student")
        post_type = post.get("post_type", "music")
        post_id = post["id"]

        if role == "admin" and post_type == "announcement":
            css_class = "post-card announcement-post"
        elif role == "admin":
            css_class = "post-card admin-post"
        else:
            css_class = "post-card normal-post"

    
        content = f"""
        <div class=\"{css_class}\">
            <b>{post['username']}</b>
            <br>
            <small>{post['created_at']}</small>
            <br><br>
            {post.get('caption') or post.get('journal_text') or ''}
        </div>
        """

        st.markdown(content, unsafe_allow_html=True)

        if post.get("video_path") and os.path.exists(post["video_path"]):
            st.video(post["video_path"])

            cursor.execute("SELECT id FROM likes WHERE user_id=%s AND post_id=%s", (current_user, post_id))
        liked = cursor.fetchone()

        like_col, delete_col = st.columns([2, 1])

        with like_col:
            if liked:
                if st.button(f"💔 Unlike {post['like_count']}", key=f"u_{post_id}"):
                    cursor.execute("DELETE FROM likes WHERE user_id=%s AND post_id=%s", (current_user, post_id))
                    conn.commit()
                    st.rerun()
            else:
                if st.button(f"❤️ Like {post['like_count']}", key=f"l_{post_id}"):
                    cursor.execute("INSERT INTO likes (user_id, post_id) VALUES (%s,%s)", (current_user, post_id))
                    conn.commit()
                    st.rerun()

        with delete_col:
            can_delete = (post["user_id"] == current_user) or (current_role == "admin")
            if can_delete and st.button("🗑 Delete Post", key=f"del_{post_id}"):
                delete_post(cursor, conn, post_id)
                st.success("Post deleted")
                st.rerun()

        show_comments_section(cursor, conn, post_id, current_user)
        st.divider()
        
# =====================================================
# ============== MY MOOD POSTS SIDEBAR SECTION =========
# =====================================================
def show_my_mood_posts(cursor, conn, current_user):
    st.title("📝 My Mood Entries")

    filter_map = {
        "All Posts": None,
        "Private": "private",
        "Public": "public",
        "Follower": "followers",
    }

    if "my_posts_filter" not in st.session_state:
        st.session_state["my_posts_filter"] = "All Posts"

    c1, c2, c3, c4 = st.columns(4)
    buttons = [c1, c2, c3, c4]
    labels = list(filter_map.keys())

    for i, label in enumerate(labels):
        with buttons[i]:
            if st.button(label, use_container_width=True):
                st.session_state["my_posts_filter"] = label

    selected = st.session_state["my_posts_filter"]
    selected_visibility = filter_map[selected]

    if selected_visibility:
        cursor.execute(
            """
            SELECT id, created_at, mood, visibility, journal_text, caption, video_path
            FROM posts
            WHERE user_id=%s AND visibility=%s
            ORDER BY created_at DESC
            """,
            (current_user, selected_visibility),
        )
    else:
        cursor.execute(
            """
            SELECT id, created_at, mood, visibility, journal_text, caption, video_path
            FROM posts
            WHERE user_id=%s
            ORDER BY created_at DESC
            """,
            (current_user,),
        )

    posts = cursor.fetchall()

    st.caption(f"Showing {len(posts)} post(s) in **{selected}**")

    if not posts:
        st.info("No mood entries found for this filter.")
        return

    for post in posts:
        st.markdown(f"**{post['created_at']}** · `{post['visibility']}`")
        body = post.get("journal_text") or post.get("caption") or "(No text)"
        st.write(body)

        if post.get("video_path") and os.path.exists(post["video_path"]):
            st.video(post["video_path"])

        if st.button("🗑 Delete Post", key=f"my_del_{post['id']}"):
            delete_post(cursor, conn, post["id"])
            st.success("Post deleted")
            st.rerun()

        st.divider()
# =====================================================
# ================= FOLLOW SYSTEM ======================
# =====================================================
def follow_user(cursor, conn, current_user, target_user):
    try:
        cursor.execute("""
            INSERT INTO follows (follower_id, following_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP
        """, (current_user, target_user))

        conn.commit()

    except Exception as e:
        print("Follow error:", e)

def unfollow_user(cursor, conn, current_user, target_user):
    cursor.execute("""
        DELETE FROM follows
        WHERE follower_id=%s AND following_id=%s
    """, (current_user, target_user))
    conn.commit()
    st.success("Unfollowed!")
    

def accept_follow_request(cursor, conn, request_id, requester_id, recipient_id):
    cursor.execute("""
        UPDATE follow_requests
        SET status='accepted'
        WHERE id=%s
    """, (request_id,))

    cursor.execute("""
        INSERT IGNORE INTO follows (follower_id, following_id)
        VALUES (%s, %s)
    """, (requester_id, recipient_id))
    conn.commit()
    st.success("Follow request accepted.")


def decline_follow_request(cursor, conn, request_id):
    cursor.execute("""
        UPDATE follow_requests
        SET status='declined'
        WHERE id=%s
    """, (request_id,))
    conn.commit()
    st.info("Follow request declined.")


# =====================================================
# ================= DISCOVER USERS =====================
# =====================================================
def discover_users(cursor, conn):
    ensure_follow_requests_table(cursor, conn)

    st.title("🔍 Discover People")
    st.caption("Find classmates, view bios, and connect through follow requests.")

    current_user = st.session_state["user_id"]
   
    st.markdown("""
    <style>
    .discover-wrap {
        background: linear-gradient(140deg, rgba(200,228,214,0.45), rgba(148,205,216,0.28));
        border: 1px solid rgba(107,181,166,.25);
        padding: 1rem 1.1rem;
        border-radius: 18px;
        margin-bottom: 1rem;
    }
    .discover-card {
        background: rgba(255,255,255,0.92);
        border: 1px solid #c8e4d6;
        border-radius: 16px;
        padding: .9rem;
        margin-bottom: .8rem;
        box-shadow: 0 6px 18px rgba(0,0,0,.05);
    }
    .discover-name {
        color: #1e6357;
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: .2rem;
    }
    .discover-meta {
        color: #3a5f57;
        font-size: .88rem;
        margin-bottom: .3rem;
    }
    .discover-bio {
        color: #2f4f49;
        font-size: .92rem;
        margin: 0;
    }
    .request-chip {
        display: inline-block;
        padding: .1rem .5rem;
        border-radius: 999px;
        font-size: .78rem;
        font-weight: 600;
        color: #fff;
        background: linear-gradient(120deg, #6bb5a6, #9bc870);
    }
    </style>
    """, unsafe_allow_html=True)

    search = st.text_input("Search users", placeholder="Search by username...")

    cursor.execute("""
        SELECT fr.id, fr.requester_id, u.username, u.bio, u.profile_pic, fr.created_at
        FROM follow_requests fr
        JOIN users u ON u.id = fr.requester_id
        WHERE fr.recipient_id=%s AND fr.status='pending'
        ORDER BY fr.created_at DESC
    """, (current_user,))
    incoming_requests = cursor.fetchall()

    with st.container(border=True):
        st.subheader("📩 Follow Requests")
        if not incoming_requests:
            st.write("No pending requests right now.")
        else:
            for req in incoming_requests:
                col1, col2, col3 = st.columns([1, 5, 3])
                with col1:
                    st.image(req["profile_pic"] or DEFAULT_PROFILE_PIC, width=52)
                with col2:
                    st.markdown(f"**{req['username']}**")
                    st.caption(req["bio"] or "No bio yet.")
                with col3:
                    if st.button("Accept ✅", key=f"acc_{req['id']}"):
                        accept_follow_request(cursor, conn, req["id"], req["requester_id"], current_user)
                        st.rerun()
                    if st.button("Decline ❌", key=f"dec_{req['id']}"):
                        decline_follow_request(cursor, conn, req["id"])
                        st.rerun()

    st.markdown('<div class="discover-wrap">', unsafe_allow_html=True)
    st.subheader("🌟 Discover Students")
    
    if search:
        cursor.execute("""
           SELECT id, username, bio, profile_pic, campus_group, year_of_study
            FROM users
            WHERE username LIKE %s
        """, (f"%{search}%",))
    else:
        cursor.execute("""
            SELECT id, username, bio, profile_pic, campus_group, year_of_study
            FROM users
        """)

    users = cursor.fetchall()

    for user in users:
        if user["id"] == current_user:
            continue

        cursor.execute("""
            SELECT * FROM follows
            WHERE follower_id=%s AND following_id=%s
        """, (current_user, user["id"]))

        following = cursor.fetchone()
        cursor.execute("""
            SELECT status FROM follow_requests
            WHERE requester_id=%s AND recipient_id=%s
        """, (current_user, user["id"]))
        outgoing_request = cursor.fetchone()

        col1, col2, col3 = st.columns([1, 6, 2])

        with col1:
            st.image(user["profile_pic"] or DEFAULT_PROFILE_PIC, width=62)

        with col2:
            st.markdown('<div class="discover-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="discover-name">{user["username"]}</div>', unsafe_allow_html=True)
            campus_group = user.get("campus_group") or "Campus community"
            year = user.get("year_of_study") or "Year not set"
            st.markdown(f'<div class="discover-meta">🏫 {campus_group} • 📘 {year}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="discover-bio">{user["bio"] or "No bio yet — follow to connect!"}</p>',
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        with col3:
            if following:
                if st.button("Unfollow", key=f"u{user['id']}"):
                    unfollow_user(cursor, conn, current_user, user["id"])
                    st.rerun()
                elif outgoing_request and outgoing_request["status"] == "pending":
                    st.markdown('<span class="request-chip">Request sent</span>', unsafe_allow_html=True)
            elif outgoing_request and outgoing_request["status"] == "declined":
                if st.button("Follow Again", key=f"rf{user['id']}"):
                    follow_user(cursor, conn, current_user, user["id"])
                    st.rerun()
            else:
                if st.button("Follow", key=f"f{user['id']}"):
                    follow_user(cursor, conn, current_user, user["id"])
                    st.rerun()

        st.divider()
        st.markdown('</div>', unsafe_allow_html=True)