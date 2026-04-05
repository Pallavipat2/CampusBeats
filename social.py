# ================= IMPORTS =================
import base64
import mimetypes
import os
import uuid
from datetime import datetime

import streamlit as st
try:
    import httpx
except ImportError:
    httpx = None

from db import first_row, result_data
from spotify_playback import render_spotify_track_player


DEFAULT_PROFILE_PIC = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
UPLOAD_FOLDER = "uploads/videos"
VIDEO_BUCKET = os.getenv("SUPABASE_VIDEO_BUCKET", "post-videos")


def _is_transient_network_error(error):
    message = str(error)
    if "WinError 10035" in message or "ReadError" in message:
        return True
    if httpx is not None and isinstance(error, (httpx.ReadError, httpx.TimeoutException, httpx.ConnectError)):
        return True
    return False


def _record_query_warning():
    st.session_state["_supabase_query_warning"] = (
        "Supabase had a temporary connection hiccup. Please refresh and try again."
    )


def _consume_query_warning():
    warning = st.session_state.pop("_supabase_query_warning", None)
    if warning:
        st.warning(warning)


def _storage_public_url(storage_response):
    if isinstance(storage_response, str):
        return storage_response
    if isinstance(storage_response, dict):
        return storage_response.get("publicUrl") or storage_response.get("public_url")
    for attr in ("publicUrl", "public_url"):
        value = getattr(storage_response, attr, None)
        if value:
            return value
    return None


def _upload_video_to_storage(supabase, owner_id, uploaded_video):
    file_ext = uploaded_video.name.split(".")[-1].lower()
    file_name = f"{owner_id}/{uuid.uuid4()}.{file_ext}"
    file_bytes = uploaded_video.getvalue()

    supabase.storage.from_(VIDEO_BUCKET).upload(
        path=file_name,
        file=file_bytes,
        file_options={
            "content-type": uploaded_video.type or f"video/{file_ext}",
            "upsert": "false",
        },
    )

    public_url = _storage_public_url(
        supabase.storage.from_(VIDEO_BUCKET).get_public_url(file_name)
    )
    if not public_url:
        raise ValueError("Could not resolve the uploaded video URL.")
    return public_url


def _insert_video_post(supabase, payload):
    attempts = [
        payload,
        {**payload, "video_path": payload.get("video_url"), **({"video_url": None} if "video_url" in payload else {})},
        {key: value for key, value in payload.items() if key != "video_url"},
        {key: value for key, value in payload.items() if key != "video_path"},
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
            return
        except Exception as error:
            last_error = error
            if "column of 'posts' in the schema cache" in str(error):
                continue
            raise

    if last_error is not None:
        raise last_error


def _rows(query):
    try:
        return result_data(query.execute())
    except Exception as error:
        if _is_transient_network_error(error):
            _record_query_warning()
            return []
        raise


def _row(query):
    try:
        return first_row(query.execute())
    except Exception as error:
        if _is_transient_network_error(error):
            _record_query_warning()
            return None
        raise


def _fetch_users_by_ids(supabase, user_ids):
    if not user_ids:
        return {}
    rows = _rows(
        supabase.table("users")
        .select("id, username, email, bio, profile_pic, campus_group, year_of_study, role")
        .in_("id", sorted(user_ids))
    )
    return {row["id"]: row for row in rows}


def _fetch_songs_by_ids(supabase, song_ids):
    if not song_ids:
        return {}
    rows = _rows(
        supabase.table("songs")
        .select("id, song_name, artist_name, spotify_track_id, genre")
        .in_("id", sorted(song_ids))
    )
    return {row["id"]: row for row in rows}


def _fetch_like_counts(supabase, post_ids):
    if not post_ids:
        return {}
    likes = _rows(
        supabase.table("likes").select("post_id").in_("post_id", sorted(post_ids))
    )
    counts = {post_id: 0 for post_id in post_ids}
    for like in likes:
        counts[like["post_id"]] = counts.get(like["post_id"], 0) + 1
    return counts


def _fetch_comment_counts(supabase, post_ids):
    if not post_ids:
        return {}
    comments = _rows(
        supabase.table("comments").select("post_id").in_("post_id", sorted(post_ids))
    )
    counts = {post_id: 0 for post_id in post_ids}
    for comment in comments:
        counts[comment["post_id"]] = counts.get(comment["post_id"], 0) + 1
    return counts


def _fetch_following_ids(supabase, current_user):
    rows = _rows(
        supabase.table("follows").select("following_id").eq("follower_id", current_user)
    )
    return {row["following_id"] for row in rows}


def format_post_time(created_at):
    if created_at is None:
        return "Unknown time"

    if isinstance(created_at, str):
        normalized = created_at.replace("Z", "+00:00")
        try:
            created_at = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    created_at = datetime.strptime(created_at, fmt)
                    break
                except ValueError:
                    continue

    if isinstance(created_at, datetime):
        return created_at.strftime("%d %b %Y, %I:%M %p")

    return str(created_at)


def get_image_src(image_path):
    if not image_path:
        return DEFAULT_PROFILE_PIC

    if str(image_path).startswith(("http://", "https://", "data:")):
        return image_path

    if os.path.exists(image_path):
        mime_type, _ = mimetypes.guess_type(image_path)
        mime_type = mime_type or "image/jpeg"
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    return DEFAULT_PROFILE_PIC


def get_video_src(video_path):
    if not video_path:
        return None

    video_path = str(video_path)

    if video_path.startswith(("http://", "https://", "data:")):
        return {"kind": "url", "value": video_path}

    if os.path.exists(video_path):
        return {"kind": "file", "value": video_path}

    normalized_path = os.path.normpath(video_path)
    if os.path.exists(normalized_path):
        return {"kind": "file", "value": normalized_path}

    workspace_relative = os.path.normpath(os.path.join(os.getcwd(), video_path))
    if os.path.exists(workspace_relative):
        return {"kind": "file", "value": workspace_relative}

    return None


def render_video(video_src):
    if not video_src:
        return

    if video_src.get("kind") == "url":
        st.video(video_src["value"])
        return

    if video_src.get("kind") == "file":
        with open(video_src["value"], "rb") as video_file:
            st.video(video_file.read())


def _post_sort_key(post):
    priority = 2
    if post.get("role") == "admin" and post.get("post_type") == "announcement":
        priority = 0
    elif post.get("role") == "admin":
        priority = 1
    created_at = post.get("created_at") or ""
    return (priority, created_at)


def _enriched_posts(supabase, posts):
    user_ids = {post["user_id"] for post in posts}
    song_ids = {post["song_id"] for post in posts if post.get("song_id") is not None}
    post_ids = {post["id"] for post in posts}

    users_by_id = _fetch_users_by_ids(supabase, user_ids)
    songs_by_id = _fetch_songs_by_ids(supabase, song_ids)
    like_counts = _fetch_like_counts(supabase, post_ids)
    comment_counts = _fetch_comment_counts(supabase, post_ids)

    enriched = []
    for post in posts:
        user = users_by_id.get(post["user_id"], {})
        song = songs_by_id.get(post.get("song_id"), {})
        enriched.append(
            {
                **post,
                "username": user.get("username", "Unknown user"),
                "profile_pic": user.get("profile_pic"),
                "role": user.get("role", "student"),
                "song_name": song.get("song_name"),
                "artist_name": song.get("artist_name"),
                "spotify_track_id": song.get("spotify_track_id"),
                "like_count": like_counts.get(post["id"], 0),
                "comment_count": comment_counts.get(post["id"], 0),
            }
        )

    enriched.sort(key=_post_sort_key)
    announcement_posts = [post for post in enriched if _post_sort_key(post)[0] == 0]
    admin_posts = [post for post in enriched if _post_sort_key(post)[0] == 1]
    normal_posts = [post for post in enriched if _post_sort_key(post)[0] == 2]

    def _sort_desc(items):
        return sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)

    return _sort_desc(announcement_posts) + _sort_desc(admin_posts) + _sort_desc(normal_posts)


def show_video_upload(supabase, current_user):
    st.subheader("Upload Music Video")

    caption = st.text_area("Caption", key="video_caption")
    mood = st.selectbox(
        "Choose your mood",
        [
            "Happy", "Sad", "Stressed", "Excited", "Overthinking", "Content",
            "Calm", "Hopeful", "Proud", "Grateful", "Inspired", "Lonely",
            "Tired", "Disappointed", "Anxious", "Overwhelmed", "Motivated",
            "Hopeless", "Enraged", "Lost", "Nostalgic",
        ],
    )
    visibility = st.selectbox("Visibility", ["public", "followers", "private"], key="video_visibility")
    uploaded_video = st.file_uploader(
        "Upload a music video",
        type=["mp4", "mov", "avi", "mkv"],
        key="video_uploader",
    )

    if st.button("Post Video"):
        if uploaded_video is None:
            st.error("Please upload a video")
            return

        try:
            video_url = _upload_video_to_storage(supabase, current_user, uploaded_video)

            _insert_video_post(
                supabase,
                {
                    "user_id": current_user,
                    "song_id": None,
                    "mood": mood,
                    "journal_text": caption,
                    "visibility": visibility,
                    "video_url": video_url,
                    "caption": caption,
                },
            )

            st.success("Video uploaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Upload failed: {e}")


def can_view_post(post, current_user, following_ids):
    if post["user_id"] == current_user:
        return True
    if post.get("visibility") == "public":
        return True
    if post.get("visibility") == "followers" and post["user_id"] in following_ids:
        return True
    return False


def delete_post(supabase, post_id):
    try:
        if st.session_state.get("role") == "admin":
            supabase.rpc("admin_delete_post", {"target_post_id": str(post_id)}).execute()
        else:
            supabase.table("likes").delete().eq("post_id", post_id).execute()
            supabase.table("comments").delete().eq("post_id", post_id).execute()
            supabase.table("posts").delete().eq("id", post_id).execute()
    except Exception as error:
        if 'row-level security policy for table "posts"' in str(error):
            st.error(
                "Supabase is blocking post deletion on `public.posts`. "
                "Please re-run the posts RLS section in `supabase_public_users_migration.sql`."
            )
            return False
        if "admin_delete_post" in str(error):
            st.error(
                "Supabase has not picked up the admin delete function yet. "
                "Please re-run `supabase_public_users_migration.sql`, then refresh the app."
            )
            return False
        if 'row-level security policy for table "likes"' in str(error):
            st.error(
                "Supabase is blocking like cleanup on `public.likes`. "
                "Please re-run the likes RLS section in `supabase_public_users_migration.sql`."
            )
            return False
        if 'row-level security policy for table "comments"' in str(error):
            st.error(
                "Supabase is blocking comment cleanup on `public.comments`. "
                "Please re-run the comments RLS section in `supabase_public_users_migration.sql`."
            )
            return False
        st.error(f"Could not delete post: {error}")
        return False
    return True


def delete_comment(supabase, comment_id):
    try:
        supabase.rpc("delete_comment_authorized", {"target_comment_id": str(comment_id)}).execute()
    except Exception as error:
        if "delete_comment_authorized" in str(error):
            st.error(
                "Supabase has not picked up the comment delete function yet. "
                "Please re-run `supabase_public_users_migration.sql`, then refresh the app."
            )
            return False
        if 'row-level security policy for table "comments"' in str(error):
            st.error(
                "Supabase is blocking comment deletion on `public.comments`. "
                "Please re-run the comments RLS section in `supabase_public_users_migration.sql`."
            )
            return False
        st.error(f"Could not delete comment: {error}")
        return False
    return True


def create_comment(supabase, post_id, comment_text):
    try:
        supabase.rpc(
            "create_comment_authorized",
            {
                "target_post_id": str(post_id),
                "new_comment_text": comment_text,
            },
        ).execute()
    except Exception as error:
        if "create_comment_authorized" in str(error):
            st.error(
                "Supabase has not picked up the comment create function yet. "
                "Please re-run `supabase_public_users_migration.sql`, then refresh the app."
            )
            return False
        if 'row-level security policy for table "comments"' in str(error):
            st.error(
                "Supabase is blocking comment creation on `public.comments`. "
                "Please re-run the comments SQL in `supabase_public_users_migration.sql`."
            )
            return False
        st.error(f"Could not post comment: {error}")
        return False
    return True


def ensure_student_follows_admin(supabase, user_id):
    user = _row(
        supabase.table("users").select("id, role").eq("id", user_id).limit(1)
    )
    if not user or user.get("role") == "admin":
        return

    admin_user = _row(
        supabase.table("users").select("id").eq("role", "admin").order("id").limit(1)
    )
    if not admin_user:
        return

    try:
        supabase.table("follows").upsert(
            {"follower_id": user_id, "following_id": admin_user["id"]},
            on_conflict="follower_id,following_id",
        ).execute()
    except Exception:
        # Keep the feed usable even before the follow-table RLS migration is applied.
        return


def show_comments_section(supabase, post_id, current_user, post_owner_id):
    comments_key = f"show_comments_{post_id}"

    if comments_key not in st.session_state:
        st.session_state[comments_key] = False

    toggle_label = "Hide comments" if st.session_state[comments_key] else "Show comments"
    if st.button(toggle_label, key=f"toggle_comments_{post_id}"):
        st.session_state[comments_key] = not st.session_state[comments_key]
        st.rerun()

    if not st.session_state[comments_key]:
        return

    comments = _rows(
        supabase.table("comments")
        .select("id, post_id, user_id, comment_text, created_at")
        .eq("post_id", post_id)
        .order("created_at")
    )

    comment_users = _fetch_users_by_ids(supabase, {comment["user_id"] for comment in comments})

    if comments:
        for comment in comments:
            username = comment_users.get(comment["user_id"], {}).get("username", "Unknown user")
            st.caption(f"**{username}** · {format_post_time(comment.get('created_at'))}")
            st.markdown(f'<div class="comment-body">{comment["comment_text"]}</div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("No comments yet.")

    new_comment = st.text_input("Add a comment", key=f"comment_input_{post_id}")
    if st.button("Post Comment", key=f"comment_btn_{post_id}"):
        if not new_comment.strip():
            st.error("Comment cannot be empty")
            return

        if create_comment(supabase, post_id, new_comment.strip()):
            st.success("Comment posted")
            st.rerun()


def show_comments_section_managed(supabase, post_id, current_user, post_owner_id):
    comments_key = f"show_comments_{post_id}"

    if comments_key not in st.session_state:
        st.session_state[comments_key] = False

    if not st.session_state[comments_key]:
        return

    comments = _rows(
        supabase.table("comments")
        .select("id, post_id, user_id, comment_text, created_at")
        .eq("post_id", post_id)
        .order("created_at")
    )

    comment_users = _fetch_users_by_ids(supabase, {comment["user_id"] for comment in comments})

    if comments:
        for comment in comments:
            username = comment_users.get(comment["user_id"], {}).get("username", "Unknown user")
            can_delete_comment = (
                st.session_state.get("role") == "admin"
                or comment["user_id"] == current_user
                or post_owner_id == current_user
            )
            with st.container(border=True):
                meta_col, delete_col = st.columns([6, 1])
            with meta_col:
                st.caption(f"**{username}** · {format_post_time(comment.get('created_at'))}")
            with delete_col:
                if can_delete_comment and st.button("Delete", key=f"del_comment_{comment['id']}"):
                    if delete_comment(supabase, comment["id"]):
                        st.success("Comment deleted")
                        st.rerun()
            st.write(comment["comment_text"])
    else:
        st.caption("No comments yet.")

    new_comment = st.text_input("Add a comment", key=f"comment_input_managed_{post_id}")
    if st.button("Post Comment", key=f"comment_btn_managed_{post_id}"):
        if not new_comment.strip():
            st.error("Comment cannot be empty")
            return

        supabase.table("comments").insert(
            {
                "post_id": post_id,
                "user_id": current_user,
                "comment_text": new_comment.strip(),
            }
        ).execute()
        st.success("Comment posted")
        st.rerun()


def show_comments_section_polished(supabase, post_id, current_user, post_owner_id):
    comments_key = f"show_comments_{post_id}"

    if comments_key not in st.session_state:
        st.session_state[comments_key] = False

    if not st.session_state[comments_key]:
        return

    comments = _rows(
        supabase.table("comments")
        .select("id, post_id, user_id, comment_text, created_at")
        .eq("post_id", post_id)
        .order("created_at")
    )

    comment_users = _fetch_users_by_ids(supabase, {comment["user_id"] for comment in comments})

    if comments:
        for comment in comments:
            comment_user = comment_users.get(comment["user_id"], {})
            username = comment_user.get("username", "Unknown user")
            comment_profile_pic = get_image_src(comment_user.get("profile_pic") or DEFAULT_PROFILE_PIC)
            can_delete_comment = (
                st.session_state.get("role") == "admin"
                or comment["user_id"] == current_user
                or post_owner_id == current_user
            )
            with st.container(border=True):
                avatar_col, meta_col, delete_col = st.columns([0.7, 5.3, 1])
                with avatar_col:
                    st.image(comment_profile_pic, width=28)
                with meta_col:
                    st.markdown(
                        f"**{username}**  \n<small>{format_post_time(comment.get('created_at'))}</small>",
                        unsafe_allow_html=True,
                    )
                with delete_col:
                    if can_delete_comment:
                        with st.popover("⋯", use_container_width=True):
                            if st.button(
                                "Delete comment",
                                key=f"del_comment_polished_{comment['id']}",
                                use_container_width=True,
                            ):
                                if delete_comment(supabase, comment["id"]):
                                    st.success("Comment deleted")
                                    st.rerun()
                st.markdown(comment["comment_text"])
    else:
        st.caption("No comments yet.")

    composer_col, action_col = st.columns([5, 1.2])
    with composer_col:
        new_comment = st.text_input(
            "Write a comment...",
            key=f"comment_input_polished_{post_id}",
            label_visibility="collapsed",
            placeholder="Write a comment...",
        )
    with action_col:
        post_comment = st.button(
            "Post",
            key=f"comment_btn_polished_{post_id}",
            use_container_width=True,
        )

    if post_comment:
        if not new_comment.strip():
            st.error("Comment cannot be empty")
            return

        supabase.table("comments").insert(
            {
                "post_id": post_id,
                "user_id": current_user,
                "comment_text": new_comment.strip(),
            }
        ).execute()
        st.success("Comment posted")
        st.rerun()


def show_feed(supabase, current_user):
    ensure_student_follows_admin(supabase, current_user)
    current_role = st.session_state.get("role", "student")
    _consume_query_warning()

    st.markdown(
        """
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
        margin-bottom: 0;
        box-shadow: none;
        animation: cb-card-in 0.35s ease both;
        transition: none;
    }
    .admin-post {
        background: linear-gradient(135deg, #F9A822 0%, #D96C80 100%);
        border: 1px solid rgba(110, 76, 64, 0.18);
    }
    .admin-post,
    .admin-post b,
    .admin-post small,
    .admin-post .post-text,
    .admin-post .post-song-line {
        color: #17352d !important;
        text-shadow: none;
    }
    .announcement-post {
        background: linear-gradient(135deg, #F9A822 0%, #D96C80 100%);
        border: 1px solid rgba(110, 76, 64, 0.18);
        box-shadow: none;
        position: relative;
        overflow: hidden;
    }
    .announcement-post,
    .announcement-post b,
    .announcement-post small,
    .announcement-post .post-text,
    .announcement-post .post-song-line {
        color: #17352d !important;
        text-shadow: none;
    }
    .announcement-post::after {
        content: none;
    }
    .normal-post {
        background: #ffffff;
        border: 1px solid rgba(200, 228, 214, 0.78);
        backdrop-filter: none;
        -webkit-backdrop-filter: none;
    }
    .post-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 6px;
    }
    .post-avatar {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        object-fit: cover;
        background: rgba(255,255,255,0.95);
        border: 2px solid rgba(255,255,255,0.92);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        flex-shrink: 0;
    }
    .post-user-meta {
        display: flex;
        flex-direction: column;
        gap: 0;
        line-height: 1.1;
    }
    .post-user-meta b {
        margin: 0;
    }
    .post-user-meta small {
        margin: 0;
        line-height: 1.1;
    }
    .post-song-line {
        display: block;
        margin: 10px 0 14px 0;
    }
    .post-text {
        margin-top: 12px;
    }
    .post-shell {
        margin-bottom: 20px;
    }
    .post-engagement {
        margin-top: 14px;
        padding-top: 10px;
        border-top: 1px solid rgba(18, 61, 54, 0.08);
        color: #40655d;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .post-actions {
        margin-top: 8px;
        padding-top: 6px;
        border-top: 1px solid rgba(18, 61, 54, 0.08);
    }
    .post-comment-block {
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid rgba(18, 61, 54, 0.08);
    }
    .comment-shell {
        padding: 0.55rem 0.2rem 0.7rem 0.2rem;
        border-bottom: 1px solid rgba(18, 61, 54, 0.06);
    }
    .comment-body {
        color: #244b43;
        font-size: 0.96rem;
        margin-top: 0.15rem;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff !important;
        border: 1px solid rgba(200, 228, 214, 0.78) !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08) !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] > div {
        background: #ffffff !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
        background: #ffffff !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] {
        background: #ffffff !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] {
        background: #ffffff !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stElementContainer"] {
        background: #ffffff !important;
    }
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] .stButton,
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] .stTextInput,
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] .stCaptionContainer,
    .feed-posts [data-testid="stVerticalBlockBorderWrapper"] .stColumns {
        background: #ffffff !important;
    }
    .feed-video-frame {
        max-width: 300px;
        margin: 14px auto 10px auto;
        border-radius: 24px;
        overflow: hidden;
        box-shadow: 0 14px 30px rgba(0,0,0,0.16);
        background: rgba(12, 24, 22, 0.08);
        border: 1px solid rgba(107, 181, 166, 0.22);
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    following_ids = _fetch_following_ids(supabase, current_user)

    if current_role != "admin":
        if "feed_view_mode" not in st.session_state:
            st.session_state["feed_view_mode"] = "all"

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            if st.button("All Visible Posts", use_container_width=True):
                st.session_state["feed_view_mode"] = "all"
        with filter_col2:
            if st.button("My Circle", use_container_width=True):
                st.session_state["feed_view_mode"] = "circle"

        st.caption(
            "Showing your posts and people you follow."
            if st.session_state["feed_view_mode"] == "circle"
            else "Showing all posts you are allowed to view."
        )
    else:
        st.session_state["feed_view_mode"] = "all"
        st.caption("Showing all posts you are allowed to view.")

    posts = _rows(
        supabase.table("posts").select("*").order("created_at", desc=True)
    )
    posts = _enriched_posts(supabase, posts)
    posts = [post for post in posts if can_view_post(post, current_user, following_ids)]

    if current_role != "admin" and st.session_state["feed_view_mode"] == "circle":
        posts = [
            post for post in posts
            if post["user_id"] == current_user or post["user_id"] in following_ids
        ]

    if not posts:
        if current_role != "admin" and st.session_state["feed_view_mode"] == "circle":
            st.info("No posts yet from you or the people you follow.")
        else:
            st.info("No posts yet.")
        return

    st.markdown('<div class="feed-posts">', unsafe_allow_html=True)
    for post in posts:
        role = post.get("role", "student")
        post_type = post.get("post_type", "music")
        post_id = post["id"]
        posted_at = format_post_time(post.get("created_at"))
        spotify_track_id = post.get("spotify_track_id")
        post_text = post.get("caption") or post.get("journal_text") or ""
        profile_pic = get_image_src(post.get("profile_pic") or DEFAULT_PROFILE_PIC)
        image_path = post.get("image_path") or post.get("image_url")
        video_path = get_video_src(post.get("video_path") or post.get("video_url"))
        attachment_link = post.get("attachment_link")
        has_other_attachments = bool(image_path or attachment_link)

        if role == "admin" and post_type == "announcement":
            css_class = "post-card announcement-post"
        elif role == "admin":
            css_class = "post-card admin-post"
        else:
            css_class = "post-card normal-post"

        card_content = f"""
            <div class="{css_class}">
            <div class="post-header">
                <img src="{profile_pic}" class="post-avatar" alt="{post['username']} profile picture">
                <div class="post-user-meta">
                    <b>{post['username']}</b>
                    <small>Posted: {posted_at}</small>
                </div>
            </div>
        """

        can_delete = (post["user_id"] == current_user) or (current_role == "admin")
        liked = _row(
            supabase.table("likes")
            .select("id")
            .eq("user_id", current_user)
            .eq("post_id", post_id)
            .limit(1)
        )

        with st.container(border=True):
            st.markdown(card_content, unsafe_allow_html=True)

            if spotify_track_id:
                render_spotify_track_player(
                    spotify_track_id,
                    key_prefix=f"feed_{post_id}_{spotify_track_id}",
                    compact=True,
                )

            if post_text:
                st.markdown(f'<div class="post-text">{post_text}</div>', unsafe_allow_html=True)

            if video_path:
                left_col, center_col, right_col = st.columns([1.2, 1.6, 1.2])
                with center_col:
                    st.markdown('<div class="feed-video-frame">', unsafe_allow_html=True)
                    render_video(video_path)
                    st.markdown("</div>", unsafe_allow_html=True)

            if has_other_attachments:
                if image_path and os.path.exists(image_path):
                    st.image(image_path, use_container_width=True)
                if attachment_link:
                    st.link_button("Open attachment link", attachment_link)

            st.markdown(
                f'<div class="post-engagement">{post["like_count"]} likes · {post.get("comment_count", 0)} comments</div>',
                unsafe_allow_html=True,
            )

            action_col1, action_col2, action_col3 = st.columns([1.2, 1.2, 0.45])

            with action_col1:
                like_label = "♥ Liked" if liked else "♡ Like"
                if st.button(like_label, key=f"like_action_{post_id}", use_container_width=True):
                    if liked:
                        supabase.table("likes").delete().eq("user_id", current_user).eq("post_id", post_id).execute()
                    else:
                        supabase.table("likes").upsert(
                            {"user_id": current_user, "post_id": post_id},
                            on_conflict="user_id,post_id",
                        ).execute()
                    st.rerun()

            with action_col2:
                comment_toggle_label = "💬 Hide comments" if st.session_state.get(f"show_comments_{post_id}") else "💬 Comments"
                if st.button(comment_toggle_label, key=f"comment_toggle_{post_id}", use_container_width=True):
                    st.session_state[f"show_comments_{post_id}"] = not st.session_state.get(f"show_comments_{post_id}", False)
                    st.rerun()

            with action_col3:
                if can_delete:
                    with st.popover("⋯", use_container_width=True):
                        st.caption("Post options")
                        if st.button("Delete post", key=f"del_{post_id}", use_container_width=True):
                            if delete_post(supabase, post_id):
                                st.success("Post deleted")
                                st.rerun()

            st.markdown('<div class="post-comment-block">', unsafe_allow_html=True)
            show_comments_section_polished(supabase, post_id, current_user, post["user_id"])
            st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
    st.markdown("</div>", unsafe_allow_html=True)


def show_my_mood_posts(supabase, current_user):
    st.title("My Mood Entries")

    filter_map = {
        "All Posts": None,
        "Private": "private",
        "Public": "public",
        "Follower": "followers",
        "Uploads": "uploads",
    }

    if "my_posts_filter" not in st.session_state:
        st.session_state["my_posts_filter"] = "All Posts"

    c1, c2, c3, c4, c5 = st.columns(5)
    buttons = [c1, c2, c3, c4, c5]
    labels = list(filter_map.keys())

    for i, label in enumerate(labels):
        with buttons[i]:
            if st.button(label, use_container_width=True):
                st.session_state["my_posts_filter"] = label

    selected = st.session_state["my_posts_filter"]
    selected_visibility = filter_map[selected]

    query = (
        supabase.table("posts")
        .select("*")
        .eq("user_id", current_user)
        .order("created_at", desc=True)
    )
    if selected_visibility and selected_visibility != "uploads":
        query = query.eq("visibility", selected_visibility)

    posts = result_data(query.execute())
    if selected_visibility == "uploads":
        posts = [
            post for post in posts
            if post.get("video_path") or post.get("video_url") or post.get("image_path") or post.get("image_url") or post.get("attachment_link")
        ]
    songs_by_id = _fetch_songs_by_ids(supabase, {post["song_id"] for post in posts if post.get("song_id")})

    st.caption(f"Showing {len(posts)} post(s) in **{selected}**")

    if not posts:
        st.info("No mood entries found for this filter.")
        return

    for post in posts:
        song = songs_by_id.get(post.get("song_id"), {})
        created_at = format_post_time(post.get("created_at"))
        st.markdown(f"**{created_at}** · `{post['visibility']}`")

        if song.get("song_name") and song.get("artist_name"):
            st.markdown(f"**Song:** {song['song_name']} by {song['artist_name']}")
        elif song.get("song_name"):
            st.markdown(f"**Song:** {song['song_name']}")

        if song.get("spotify_track_id"):
            render_spotify_track_player(
                song["spotify_track_id"],
                key_prefix=f"mypost_{post['id']}_{song['spotify_track_id']}",
                compact=True,
            )

        body = post.get("journal_text") or post.get("caption") or "(No text)"
        st.write(body)

        video_path = get_video_src(post.get("video_path") or post.get("video_url"))
        if video_path:
            left_col, center_col, right_col = st.columns([1.2, 1.6, 1.2])
            with center_col:
                st.markdown('<div class="feed-video-frame">', unsafe_allow_html=True)
                render_video(video_path)
                st.markdown("</div>", unsafe_allow_html=True)

        if st.button("Delete Post", key=f"my_del_{post['id']}"):
            if delete_post(supabase, post["id"]):
                st.success("Post deleted")
                st.rerun()

        st.divider()


def follow_user(supabase, current_user, target_user):
    try:
        current_user_data = _row(
            supabase.table("users").select("role").eq("id", current_user).limit(1)
        )
        target_user_data = _row(
            supabase.table("users").select("role").eq("id", target_user).limit(1)
        )

        if not current_user_data or not target_user_data:
            st.error("User not found.")
            return

        if current_user_data["role"] == "admin":
            st.info("Admin accounts cannot follow other users.")
            return

        if target_user_data["role"] == "admin":
            supabase.table("follows").upsert(
                {"follower_id": current_user, "following_id": target_user},
                on_conflict="follower_id,following_id",
            ).execute()
            st.success("You are now following the admin account.")
            return

        supabase.table("follow_requests").upsert(
            {
                "requester_id": current_user,
                "recipient_id": target_user,
                "status": "pending",
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="requester_id,recipient_id",
        ).execute()
        st.success("Follow request sent.")
    except Exception as e:
        st.error(f"Follow error: {e}")


def unfollow_user(supabase, current_user, target_user):
    supabase.table("follows").delete().eq("follower_id", current_user).eq("following_id", target_user).execute()
    st.success("Unfollowed!")


def accept_follow_request(supabase, request_id, requester_id, recipient_id):
    try:
        supabase.table("follow_requests").update(
            {"status": "accepted", "updated_at": datetime.utcnow().isoformat()}
        ).eq("id", request_id).execute()
        supabase.table("follows").upsert(
            {"follower_id": requester_id, "following_id": recipient_id},
            on_conflict="follower_id,following_id",
        ).execute()
        st.success("Follow request accepted.")
    except Exception as error:
        if 'row-level security policy for table "follows"' in str(error):
            st.error(
                "Supabase is blocking follow acceptance on `public.follows`. "
                "Please re-run the follows RLS section in `supabase_public_users_migration.sql`."
            )
            return
        raise


def decline_follow_request(supabase, request_id):
    supabase.table("follow_requests").update(
        {"status": "declined", "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", request_id).execute()
    st.info("Follow request declined.")


def unsend_follow_request(supabase, requester_id, recipient_id):
    supabase.table("follow_requests").delete().eq("requester_id", requester_id).eq("recipient_id", recipient_id).eq("status", "pending").execute()
    st.info("Follow request unsent.")


def discover_users(supabase):
    ensure_student_follows_admin(supabase, st.session_state["user_id"])
    _consume_query_warning()

    st.title("Discover People")
    st.caption("Find classmates, view bios, and connect through follow requests.")

    current_user = st.session_state["user_id"]
    current_role = st.session_state.get("role", "student")

    st.markdown(
        """
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
    .request-status {
        color: #2b7a69;
        font-size: .82rem;
        font-weight: 700;
        margin-top: .35rem;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    search = st.text_input("Search users", placeholder="Search by username...")

    followers_rows = _rows(
        supabase.table("follows").select("follower_id").eq("following_id", current_user)
    )
    following_rows = _rows(
        supabase.table("follows").select("following_id").eq("follower_id", current_user)
    )
    followers_count = len(followers_rows)
    following_count = len(following_rows)

    if "show_followers_list" not in st.session_state:
        st.session_state["show_followers_list"] = False
    if "show_following_list" not in st.session_state:
        st.session_state["show_following_list"] = False

    network_col1, network_col2 = st.columns(2)
    with network_col1:
        followers_label = (
            f"Hide Followers ({followers_count})"
            if st.session_state["show_followers_list"]
            else f"Show Followers ({followers_count})"
        )
        if st.button(followers_label, use_container_width=True):
            st.session_state["show_followers_list"] = not st.session_state["show_followers_list"]
            st.rerun()

    with network_col2:
        following_label = (
            f"Hide Following ({following_count})"
            if st.session_state["show_following_list"]
            else f"Show Following ({following_count})"
        )
        if st.button(following_label, use_container_width=True):
            st.session_state["show_following_list"] = not st.session_state["show_following_list"]
            st.rerun()

    incoming_requests = _rows(
        supabase.table("follow_requests")
        .select("id, requester_id, created_at, status")
        .eq("recipient_id", current_user)
        .eq("status", "pending")
        .order("created_at", desc=True)
    )
    incoming_users = _fetch_users_by_ids(supabase, {req["requester_id"] for req in incoming_requests})

    with st.expander(f"Follow Requests ({len(incoming_requests)})", expanded=bool(incoming_requests)):
        if not incoming_requests:
            st.write("No pending requests right now.")
        else:
            for req in incoming_requests:
                req_user = incoming_users.get(req["requester_id"], {})
                col1, col2, col3 = st.columns([1, 5, 3])
                with col1:
                    st.image(req_user.get("profile_pic") or DEFAULT_PROFILE_PIC, width=52)
                with col2:
                    st.markdown(f"**{req_user.get('username', 'Unknown user')}**")
                    st.caption(req_user.get("bio") or "No bio yet.")
                with col3:
                    if st.button("Accept", key=f"acc_{req['id']}"):
                        accept_follow_request(supabase, req["id"], req["requester_id"], current_user)
                        st.rerun()
                    if st.button("Decline", key=f"dec_{req['id']}"):
                        decline_follow_request(supabase, req["id"])
                        st.rerun()

    if st.session_state["show_followers_list"]:
        followers = list(_fetch_users_by_ids(supabase, {row["follower_id"] for row in followers_rows}).values())
        with st.container(border=True):
            st.subheader("Followers")
            if not followers:
                st.write("No followers yet.")
            else:
                for follower in sorted(followers, key=lambda item: item.get("username", "").lower()):
                    col1, col2 = st.columns([1, 6])
                    with col1:
                        st.image(follower.get("profile_pic") or DEFAULT_PROFILE_PIC, width=52)
                    with col2:
                        st.markdown(f"**{follower.get('username', 'Unknown user')}**")
                        st.caption(follower.get("bio") or "No bio yet.")

    if st.session_state["show_following_list"]:
        following_users = list(_fetch_users_by_ids(supabase, {row["following_id"] for row in following_rows}).values())
        with st.container(border=True):
            st.subheader("Following")
            if not following_users:
                st.write("Not following anyone yet.")
            else:
                for followed_user in sorted(following_users, key=lambda item: item.get("username", "").lower()):
                    col1, col2 = st.columns([1, 6])
                    with col1:
                        st.image(followed_user.get("profile_pic") or DEFAULT_PROFILE_PIC, width=52)
                    with col2:
                        st.markdown(f"**{followed_user.get('username', 'Unknown user')}**")
                        st.caption(followed_user.get("bio") or "No bio yet.")

    st.markdown('<div class="discover-wrap">', unsafe_allow_html=True)
    st.subheader("Discover Students")

    users_query = (
        supabase.table("users")
        .select("id, username, bio, profile_pic, campus_group, year_of_study, role")
        .neq("role", "admin")
        .order("username")
    )
    if search:
        users_query = users_query.ilike("username", f"%{search}%")
    users = result_data(users_query.execute())

    following_set = {row["following_id"] for row in following_rows}
    outgoing_requests = _rows(
        supabase.table("follow_requests").select("recipient_id, status").eq("requester_id", current_user)
    )
    outgoing_status = {row["recipient_id"]: row["status"] for row in outgoing_requests}

    for user in users:
        if user["id"] == current_user:
            continue

        col1, col2, col3 = st.columns([1, 6, 2])

        with col1:
            st.image(user.get("profile_pic") or DEFAULT_PROFILE_PIC, width=62)

        with col2:
            st.markdown('<div class="discover-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="discover-name">{user["username"]}</div>', unsafe_allow_html=True)
            if outgoing_status.get(user["id"]) == "pending":
                st.markdown('<div class="request-status">Request sent</div>', unsafe_allow_html=True)
            campus_group = user.get("campus_group") or "Campus community"
            year = user.get("year_of_study") or "Year not set"
            st.markdown(f'<div class="discover-meta">{campus_group} • {year}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="discover-bio">{user.get("bio") or "No bio yet - follow to connect!"}</p>',
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col3:
            if current_role == "admin":
                st.caption("Admin cannot follow accounts")
            else:
                if user["id"] in following_set:
                    if st.button("Unfollow", key=f"u{user['id']}"):
                        unfollow_user(supabase, current_user, user["id"])
                        st.rerun()
                elif outgoing_status.get(user["id"]) == "pending":
                    if st.button("Unsend", key=f"unsend_{user['id']}"):
                        unsend_follow_request(supabase, current_user, user["id"])
                        st.rerun()
                elif outgoing_status.get(user["id"]) == "declined":
                    if st.button("Follow Again", key=f"rf{user['id']}"):
                        follow_user(supabase, current_user, user["id"])
                        st.rerun()
                else:
                    if st.button("Follow", key=f"f{user['id']}"):
                        follow_user(supabase, current_user, user["id"])
                        st.rerun()

        st.divider()

    st.markdown("</div>", unsafe_allow_html=True)
