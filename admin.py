import streamlit as st


def admin_post_announcement(cursor, conn):
    st.subheader("📢 Post Announcement")

    announcement_text = st.text_area("Announcement")
    visibility = st.selectbox("Who can see this?", ["public", "followers", "private"])

    if st.button("Post Announcement"):
        if not announcement_text.strip():
            st.error("Announcement cannot be empty")
            return

        admin_user_id = st.session_state["user_id"]

        cursor.execute("""
            INSERT INTO posts (user_id, caption, post_type, visibility)
            VALUES (%s, %s, %s, %s)
        """, (admin_user_id, announcement_text, "announcement", visibility))

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

    st.warning("This will permanently remove the selected user and their related data if foreign keys are set with ON DELETE CASCADE.")

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