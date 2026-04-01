import os
import uuid
import streamlit as st


ADMIN_IMAGE_FOLDER = "uploads/admin_images"
ADMIN_VIDEO_FOLDER = "uploads/admin_videos"


def ensure_admin_attachment_columns(cursor, conn):
    cursor.execute("SHOW COLUMNS FROM posts LIKE 'image_path'")
    has_image_path = cursor.fetchone()
    if not has_image_path:
        cursor.execute("ALTER TABLE posts ADD COLUMN image_path VARCHAR(255) NULL")

    cursor.execute("SHOW COLUMNS FROM posts LIKE 'attachment_link'")
    has_attachment_link = cursor.fetchone()
    if not has_attachment_link:
        cursor.execute("ALTER TABLE posts ADD COLUMN attachment_link TEXT NULL")

    conn.commit()


def admin_post_announcement(cursor, conn):
    ensure_admin_attachment_columns(cursor, conn)
    st.subheader("📢 Post Announcement")

    announcement_text = st.text_area("Announcement")

    with st.expander("Add Attachments"):
        uploaded_image = st.file_uploader(
            "Add photo",
            type=["png", "jpg", "jpeg", "webp"],
            key="admin_announcement_image"
        )
        uploaded_video = st.file_uploader(
            "Add video",
            type=["mp4", "mov", "avi", "mkv"],
            key="admin_announcement_video"
        )
        attachment_link = st.text_input(
            "Add link",
            placeholder="https://...",
            key="admin_announcement_link"
        )

    if st.button("Post Announcement"):
        if not announcement_text.strip():
            st.error("Announcement cannot be empty")
            return

        admin_user_id = st.session_state["user_id"]
        image_path = None
        video_path = None

        if uploaded_image:
            os.makedirs(ADMIN_IMAGE_FOLDER, exist_ok=True)
            image_ext = uploaded_image.name.split(".")[-1]
            image_filename = f"{uuid.uuid4()}.{image_ext}"
            image_path = os.path.join(ADMIN_IMAGE_FOLDER, image_filename)
            with open(image_path, "wb") as image_file:
                image_file.write(uploaded_image.read())

        if uploaded_video:
            os.makedirs(ADMIN_VIDEO_FOLDER, exist_ok=True)
            video_ext = uploaded_video.name.split(".")[-1]
            video_filename = f"{uuid.uuid4()}.{video_ext}"
            video_path = os.path.join(ADMIN_VIDEO_FOLDER, video_filename)
            with open(video_path, "wb") as video_file:
                video_file.write(uploaded_video.read())

        cursor.execute("""
            INSERT INTO posts (user_id, caption, post_type, visibility, image_path, video_path, attachment_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            admin_user_id,
            announcement_text,
            "announcement",
            "public",
            image_path,
            video_path,
            attachment_link.strip() or None,
        ))

        conn.commit()
        st.success("Announcement posted successfully!")


def admin_remove_user(cursor, conn):
    st.subheader("🗑 Remove User")

    cursor.execute("""
        SELECT id, username, email, role
        FROM users
        WHERE role != 'admin'
        ORDER BY username
    """)
    users = cursor.fetchall()

    if not users:
        st.info("No removable users found.")
        return

    user_map = {
        f"{user['username']} ({user['email']})": user["id"]
        for user in users
    }

    selected_user_label = st.selectbox("Select user to remove", list(user_map.keys()))
    selected_user_id = user_map[selected_user_label]

    st.warning("this will permanantly delete the user")

    if st.button("Remove User"):
        cursor.execute("DELETE FROM users WHERE id = %s", (selected_user_id,))
        conn.commit()
        st.success("User removed successfully!")
        st.rerun()


def admin_dashboard(cursor, conn):
    if st.session_state.get("role") != "admin":
        st.error("Access denied")
        st.stop()

    st.title("🎓 Admin Dashboard")
    st.write("Manage announcements and community moderation here.")

    tab1, tab2 = st.tabs(["Post Announcement", "Remove User"])

    with tab1:
        admin_post_announcement(cursor, conn)

    with tab2:
        admin_remove_user(cursor, conn)
