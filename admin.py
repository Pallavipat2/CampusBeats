import os
import uuid

import streamlit as st

from db import result_data


ADMIN_IMAGE_FOLDER = "uploads/admin_images"
ADMIN_VIDEO_FOLDER = "uploads/admin_videos"


def _insert_announcement_post(supabase, payload):
    attempts = [
        payload,
        {
            **payload,
            "image_url": payload.get("image_path"),
            **({"image_path": None} if "image_path" in payload else {}),
        },
        {
            **payload,
            "video_url": payload.get("video_path"),
            **({"video_path": None} if "video_path" in payload else {}),
        },
        {
            **payload,
            "image_url": payload.get("image_path"),
            "video_url": payload.get("video_path"),
            **({"image_path": None} if "image_path" in payload else {}),
            **({"video_path": None} if "video_path" in payload else {}),
        },
    ]

    seen_signatures = set()
    last_error = None

    for attempt in attempts:
        cleaned_attempt = {key: value for key, value in attempt.items() if value is not None}
        signature = tuple(sorted(cleaned_attempt.keys()))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        try:
            supabase.table("posts").insert(cleaned_attempt).execute()
            return True
        except Exception as error:
            last_error = error
            message = str(error)
            if "column of 'posts' in the schema cache" in message:
                continue
            raise

    fallback_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"image_path", "image_url", "video_path", "video_url", "attachment_link"} and value is not None
    }
    try:
        supabase.table("posts").insert(fallback_payload).execute()
        st.warning(
            "Announcement posted without attachments because Supabase has not refreshed the "
            "`posts` schema cache for attachment columns yet."
        )
        return False
    except Exception:
        if last_error is not None:
            raise last_error
        raise


def admin_post_announcement(supabase):
    st.subheader("Post Announcement")

    announcement_text = st.text_area("Announcement")

    with st.expander("Add Attachments"):
        uploaded_image = st.file_uploader(
            "Add photo",
            type=["png", "jpg", "jpeg", "webp"],
            key="admin_announcement_image",
        )
        uploaded_video = st.file_uploader(
            "Add video",
            type=["mp4", "mov", "avi", "mkv"],
            key="admin_announcement_video",
        )
        attachment_link = st.text_input(
            "Add link",
            placeholder="https://...",
            key="admin_announcement_link",
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

        payload = {
            "user_id": admin_user_id,
            "caption": announcement_text,
            "post_type": "announcement",
            "visibility": "public",
            "image_path": image_path,
            "video_path": video_path,
            "attachment_link": attachment_link.strip() or None,
        }

        try:
            inserted_with_default_message = _insert_announcement_post(supabase, payload)
        except Exception as error:
            st.error(f"Could not post announcement: {error}")
            return

        if inserted_with_default_message:
            st.success("Announcement posted successfully!")


def admin_remove_user(supabase):
    st.subheader("Remove User")

    users = result_data(
        supabase.table("users")
        .select("id, username, email, role")
        .neq("role", "admin")
        .order("username")
        .execute()
    )

    if not users:
        st.info("No removable users found.")
        return

    user_map = {
        f"{user['username']} ({user['email']})": user["id"]
        for user in users
    }

    selected_user_label = st.selectbox("Select user to remove", list(user_map.keys()))
    selected_user_id = user_map[selected_user_label]

    st.warning("This will permanently delete the user.")

    if st.button("Remove User"):
        supabase.table("users").delete().eq("id", selected_user_id).execute()
        st.success("User removed successfully!")
        st.rerun()


def admin_dashboard(supabase):
    if st.session_state.get("role") != "admin":
        st.error("Access denied")
        st.stop()

    st.title("Admin Dashboard")
    st.write("Manage announcements and community moderation here.")

    tab1, tab2 = st.tabs(["Post Announcement", "Remove User"])

    with tab1:
        admin_post_announcement(supabase)

    with tab2:
        admin_remove_user(supabase)
