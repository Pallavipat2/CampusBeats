#importing 
import mysql.connector
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import streamlit as st

#session state initialisation
tracks=st.session_state.get("tracks",[])  
st.session_state["tracks"]=tracks

#MySql Connection
conn=mysql.connector.connect(host="localhost",user="root",password="Mithra@258",database="campusbeats")
cursor=conn.cursor()

#spotify connection
sp=spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id="8cb649fce8974345a753f93f6bc2c35a",
    client_secret="ad6b2e04fc8f4921a74ce0267d48fe11"
))

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
        
        st.write("Selected:",song_name,"-",artist_name)
        
        #album cover
        if track['album']['images']:
            st.image(track['album']['images'][0]['url'],width=200)
        
        #---------mood input--------
        mood=st.selectbox("choose your mood",["Happy","sad","calm","anxious","excited"])
        
        journal=st.text_area("Tell me more")
        
    
        if st.button("Save entry"):
            st.write("saving entry...")
            #insert song into database
            cursor.execute("""insert ignore into songs(spotify_track_id,song_name,artist_name,album_name) values(%s,%s,%s,%s)""",(spotify_track_id,song_name,artist_name,album_name))
            
            conn.commit() #mustt

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
            
            cursor.close()
            conn.close()

