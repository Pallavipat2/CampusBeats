#importing 
import mysql.connector
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os

load_dotenv()

MYSQLHOST=os.getenv("MYSQLHOST")
MYSQLUN=os.getenv("MYSQLUN")
MYSQLPW=os.getenv("MYSQLPW")
DATABASE=os.getenv("DATABASE")
CLIENTID=os.getenv("CLIENTID")
CLIENTSECRET=os.getenv("CLIENTSECRET")

#session state (login)
if "logged_in" not in st.session_state:
    st.session_state.logged_in=False

if "user_id" not in st.session_state:
    st.session_state.user_id=None



def classify_genre(genres):
    genre_text=" ".join(genres).lower()
    if "k-pop" in genre_text:
        return "K-Pop"
    elif "indian classical" in genre_text:
        return "Indian Classical"

    elif "bollywood" in genre_text:
        return "Bollywood"

    elif "rock" in genre_text:
        return "Rock"

    else:
        return "Other"

#session state initialisation
tracks=st.session_state.get("tracks",[])  
st.session_state["tracks"]=tracks

#MySql Connection
conn=mysql.connector.connect(host=MYSQLHOST,user=MYSQLUN,password=MYSQLPW,database=DATABASE)
cursor=conn.cursor(dictionary=True)

#spotify connection
sp=spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=CLIENTID,
    client_secret=CLIENTSECRET
))

menu=st.sidebar.selectbox("menu",["Login","Search Song","Register","Mood logger","Dashboard"])


if menu=="Mood Logger":
    
        #UI
        st.title("Mood music Journal")
        query=st.text_input("Search for a song:")

        #search button
        if st.button("Search"): 
            if query:  
                results=sp.search(q=query,type="track",limit=5)
                st.session_state["tracks"]=results['tracks']['items']
        tracks=st.session_state["tracks"]
        #display results
        if tracks:
                tracks=st.session_state["tracks"]
                song_options=[]             #stores songs
                #security check (must)
                for track in tracks:
                    song_options.append(
                        f"{track['name']}-{track['artists'][0]['name']}"     #formatting
                    )
                    
                selected_song=st.selectbox("Select a song:",song_options)
                
                selected_index=song_options.index(selected_song)
                track=tracks[selected_index]

                
                spotify_track_id=track['id']
                song_name=track['name']
                artist_name=track['artists'][0]['name']
                album_name=track['album']['name']
                artist_id = track['artists'][0]['id']
                artist_info = sp.artist(artist_id)
                genres = artist_info['genres']
                spotify_url=f"https://open.spotify.com/track/{spotify_track_id}"
                spotify_embed_url = f"https://open.spotify.com/embed/track/{spotify_track_id}"
                st.write("Selected:",song_name,"-",artist_name)
                st.write(f"Album: {album_name}")
                components.iframe(spotify_embed_url, height=80)
                
                #album cover
                if track['album']['images']:
                    st.image(track['album']['images'][0]['url'],width=200)
                    
                #---------mood input--------
                mood=st.selectbox("choose your mood",["Happy","sad","calm","anxious","excited"])
                
                journal=st.text_area("Tell me more")
                
            
                if st.button("Save entry"):
                    st.write("saving entry...")
                    #insert song into database
                    cursor.execute("""insert ignore into songs(spotify_track_id,song_name,artist_name,album_name,genre) values(%s,%s,%s,%s)""",(spotify_track_id,song_name,artist_name,album_name,genres))
                    
                    conn.commit() #mustt2

                    #fetch song id
                    cursor.execute("""select id from songs where spotify_track_id=%s""",(spotify_track_id,))
                    result=cursor.fetchone()
                    if result:
                        song_id=result[0]
                    else:
                        st.error("Song not found in database")
                        st.stop()
                        
                    #insert mood entry
                    cursor.execute("""insert into mood_entries(song_id, mood, journal) values(%s,%s,%s)""",(song_id,mood,journal))  
                    
                    conn.commit()
                    
                    st.success("Entry saved Successfully")
                    
elif menu=="Dashboard":
        st.header("📊 Mood Analytics Dashboard")
        cursor.execute("""SELECT mood, COUNT(*) as total FROM mood_entries GROUP BY mood""")
        mood_data=cursor.fetchall()
        moods=[row['mood'] for row in mood_data]
        counts=[row['total'] for row in mood_data]
        
        df=pd.DataFrame({"Mood":moods, "Songs":counts})
        
        cursor.execute("SELECT COUNT(*) as total FROM mood_entries")
        total_songs=cursor.fetchone()['total']
        
        
        cursor.execute("""SELECT mood, COUNT(*) as total FROM mood_entries GROUP BY mood ORDER BY total DESC LIMIT 1 """)
        dominant_mood=cursor.fetchone()
        
        #stat cards
        col1, col2= st.columns(2)
        with col1:
            st.metric("🎵 Total Songs Logged", total_songs)
            
        with  col2:
            st.metric("😌 Dominant Mood", dominant_mood['mood'])
        
       
        
        st.subheader("📊 Mood Distribution")
        st.bar_chart(df.set_index("Mood"))
        
        st.subheader("Mood Breakdown")
        st.pyplot(df.set_index("Mood").plot.pie(y="Songs",autopct='%1.1f%%').figure)
        
cursor.close()
conn.close()