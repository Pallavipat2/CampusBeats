import json
import os
import time
import uuid

import spotipy
import streamlit as st
import streamlit.components.v1 as components
from spotipy.exceptions import SpotifyOauthError
from spotipy.oauth2 import SpotifyOAuth


SPOTIFY_PLAYBACK_SCOPES = (
    "streaming user-read-email user-read-private "
    "user-read-playback-state user-modify-playback-state"
)


def _secret_or_env(*keys):
    for key in keys:
        if not key:
            continue

        if hasattr(st, "secrets") and key in st.secrets:
            value = st.secrets.get(key)
            if value:
                return value

        value = os.getenv(key)
        if value:
            return value

    return None


def _spotify_credentials():
    client_id = _secret_or_env("CLIENTID", "SPOTIPY_CLIENT_ID")
    client_secret = _secret_or_env("CLIENTSECRET", "SPOTIPY_CLIENT_SECRET")
    redirect_uri = _secret_or_env(
        "SPOTIFY_REDIRECT_URI",
        "SPOTIPY_REDIRECT_URI",
    ) or "http://localhost:8501/?spotify_auth=1"
    return client_id, client_secret, redirect_uri


def _build_oauth_client():
    client_id, client_secret, redirect_uri = _spotify_credentials()
    if not client_id or not client_secret:
        return None, (
            "Spotify playback is not configured yet. "
            "Add Spotify client credentials first."
        )

    return (
        SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SPOTIFY_PLAYBACK_SCOPES,
            open_browser=False,
            show_dialog=True,
        ),
        None,
    )


def spotify_playback_setup_message():
    _, _, redirect_uri = _spotify_credentials()
    return (
        "To unlock full-song playback, add this redirect URI in your Spotify app dashboard: "
        f"`{redirect_uri}`"
    )


def handle_spotify_oauth_callback():
    params = st.query_params
    if params.get("spotify_auth") != "1" or not params.get("code"):
        return

    if st.session_state.get("_spotify_auth_code") == params.get("code"):
        return

    oauth, oauth_error = _build_oauth_client()
    if oauth is None:
        st.session_state["spotify_playback_error"] = oauth_error
        return

    try:
        token_info = oauth.get_access_token(
            params.get("code"),
            as_dict=True,
            check_cache=False,
        )
        st.session_state["spotify_token_info"] = token_info
        st.session_state["_spotify_auth_code"] = params.get("code")
        st.session_state["spotify_playback_error"] = None

        access_token = token_info.get("access_token")
        if access_token:
            profile = spotipy.Spotify(auth=access_token).current_user()
            st.session_state["spotify_profile_name"] = (
                profile.get("display_name")
                or profile.get("id")
                or "Spotify user"
            )
    except SpotifyOauthError as error:
        st.session_state["spotify_playback_error"] = f"Spotify login failed: {error}"
    except Exception as error:
        st.session_state["spotify_playback_error"] = f"Spotify login failed: {error}"


def _refresh_token_if_needed(token_info):
    if not token_info:
        return None

    oauth, oauth_error = _build_oauth_client()
    if oauth is None:
        st.session_state["spotify_playback_error"] = oauth_error
        return None

    expires_at = token_info.get("expires_at", 0)
    if expires_at and expires_at - int(time.time()) > 60:
        return token_info

    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        return None

    try:
        refreshed = oauth.refresh_access_token(refresh_token)
        st.session_state["spotify_token_info"] = refreshed
        return refreshed
    except Exception as error:
        st.session_state["spotify_playback_error"] = f"Spotify session expired: {error}"
        return None


def get_spotify_access_token():
    token_info = st.session_state.get("spotify_token_info")
    if not token_info:
        return None

    token_info = _refresh_token_if_needed(token_info)
    if not token_info:
        return None

    return token_info.get("access_token")


def render_spotify_playback_controls():
    st.markdown("### Spotify Premium Playback")

    oauth, oauth_error = _build_oauth_client()
    if oauth is None:
        st.info(oauth_error)
        st.caption(spotify_playback_setup_message())
        return

    playback_error = st.session_state.get("spotify_playback_error")
    if playback_error:
        st.warning(playback_error)

    access_token = get_spotify_access_token()
    if access_token:
        profile_name = st.session_state.get("spotify_profile_name") or "Spotify user"
        st.success(f"Connected to Spotify as {profile_name}.")
        if st.button("Disconnect Spotify", key="spotify_disconnect"):
            st.session_state.pop("spotify_token_info", None)
            st.session_state.pop("_spotify_auth_code", None)
            st.session_state.pop("spotify_profile_name", None)
            st.session_state.pop("spotify_playback_error", None)
            st.rerun()
        return

    auth_url = oauth.get_authorize_url(state=str(uuid.uuid4()))
    st.link_button("Connect Spotify Premium", auth_url, use_container_width=True)
    st.caption(spotify_playback_setup_message())


def render_spotify_track_player(track_id, *, key_prefix, compact=False):
    access_token = get_spotify_access_token()
    track_url = f"https://open.spotify.com/track/{track_id}"

    if not access_token:
        components.iframe(
            f"https://open.spotify.com/embed/track/{track_id}",
            height=80,
        )
        if compact:
            st.caption("Connect Spotify Premium in Mood Logger to unlock full playback here.")
            return

        st.info("Connect Spotify Premium below to play the full track inside Campus Beats.")
        st.link_button("Open in Spotify", track_url, use_container_width=True)
        return

    safe_key = "".join(ch if ch.isalnum() else "_" for ch in key_prefix)
    payload = json.dumps(
        {
            "token": access_token,
            "trackUri": f"spotify:track:{track_id}",
            "playerName": f"Campus Beats {safe_key}",
        }
    )

    html = f"""
    <div id="spotify-player-{safe_key}" style="font-family: Arial, sans-serif;">
      <div id="spotify-status-{safe_key}" style="margin-bottom:8px;color:#21584e;font-size:0.95rem;">
        Preparing Spotify player...
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button id="spotify-play-{safe_key}" disabled style="border:none;border-radius:999px;padding:10px 16px;background:#1db954;color:white;font-weight:700;cursor:pointer;">
          Play full track
        </button>
        <button id="spotify-toggle-{safe_key}" disabled style="border:1px solid #1db954;border-radius:999px;padding:10px 16px;background:white;color:#1b4332;font-weight:700;cursor:pointer;">
          Pause / Resume
        </button>
        <a href="{track_url}" target="_blank" style="display:inline-flex;align-items:center;padding:10px 16px;border-radius:999px;border:1px solid #b7dccc;color:#21584e;text-decoration:none;font-weight:700;">
          Open in Spotify
        </a>
      </div>
    </div>
    <script src="https://sdk.scdn.co/spotify-player.js"></script>
    <script>
      const spotifyConfig = {payload};
      const statusEl = document.getElementById("spotify-status-{safe_key}");
      const playButton = document.getElementById("spotify-play-{safe_key}");
      const toggleButton = document.getElementById("spotify-toggle-{safe_key}");
      let player;
      let activeDeviceId = null;

      function setStatus(message) {{
        statusEl.textContent = message;
      }}

      async function transferPlayback(deviceId) {{
        await fetch("https://api.spotify.com/v1/me/player", {{
          method: "PUT",
          headers: {{
            "Authorization": "Bearer " + spotifyConfig.token,
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{ device_ids: [deviceId], play: false }})
        }});
      }}

      async function playTrack() {{
        if (!activeDeviceId) {{
          setStatus("Spotify player is still connecting...");
          return;
        }}

        setStatus("Starting playback...");
        const response = await fetch(
          "https://api.spotify.com/v1/me/player/play?device_id=" + encodeURIComponent(activeDeviceId),
          {{
            method: "PUT",
            headers: {{
              "Authorization": "Bearer " + spotifyConfig.token,
              "Content-Type": "application/json"
            }},
            body: JSON.stringify({{ uris: [spotifyConfig.trackUri] }})
          }}
        );

        if (response.ok || response.status === 204) {{
          setStatus("Full playback is active in this browser player.");
        }} else {{
          const details = await response.text();
          setStatus("Spotify playback error: " + details);
        }}
      }}

      playButton.addEventListener("click", async () => {{
        try {{
          await playTrack();
        }} catch (error) {{
          setStatus("Spotify playback error: " + error.message);
        }}
      }});

      toggleButton.addEventListener("click", async () => {{
        if (!player) {{
          return;
        }}
        try {{
          await player.togglePlay();
        }} catch (error) {{
          setStatus("Could not pause or resume playback: " + error.message);
        }}
      }});

      window.onSpotifyWebPlaybackSDKReady = () => {{
        player = new window.Spotify.Player({{
          name: spotifyConfig.playerName,
          getOAuthToken: callback => callback(spotifyConfig.token),
          volume: 0.8
        }});

        player.addListener("ready", async (data) => {{
          activeDeviceId = data.device_id;
          playButton.disabled = false;
          toggleButton.disabled = false;
          setStatus("Spotify Premium player ready. Press Play full track.");
          try {{
            await transferPlayback(activeDeviceId);
          }} catch (error) {{
            setStatus("Player connected, but transfer failed: " + error.message);
          }}
        }});

        player.addListener("not_ready", () => {{
          setStatus("Spotify player went offline. Refresh the page and reconnect if needed.");
        }});

        player.addListener("initialization_error", (data) => {{
          setStatus("Spotify initialization error: " + data.message);
        }});

        player.addListener("authentication_error", (data) => {{
          setStatus("Spotify authentication error: " + data.message);
        }});

        player.addListener("account_error", (data) => {{
          setStatus("Spotify account error: " + data.message + ". Premium is required.");
        }});

        player.addListener("playback_error", (data) => {{
          setStatus("Spotify playback error: " + data.message);
        }});

        player.connect().then((connected) => {{
          if (!connected) {{
            setStatus("Spotify could not connect in this browser.");
          }}
        }});
      }};
    </script>
    """

    components.html(html, height=135 if compact else 155)
