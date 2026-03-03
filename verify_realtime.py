import socketio
import time
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = "http://localhost:5000"
TEST_URL = "https://cafe.naver.com/ca-fe/web/cafes/12345/articles/67890"

sio = socketio.Client()

received_updates = []

@sio.on('update_participants')
def on_update_participants(data):
    print(f"Received update_participants: {len(data.get('participants', []))} participants, {data.get('total_comments')} comments")
    received_updates.append(data)

@sio.on('update_event_settings')
def on_update_settings(data):
    print(f"Received update_event_settings: {data.get('title')}")

def verify_realtime():
    try:
        sio.connect(BASE_URL)
        print("Connected to Socket.IO")
        
        # Trigger an update by calling the API
        # This simulates a new comment being found
        print("Triggering update via API...")
        # Note: We can't easily "fake" a new comment in Supabase from here without proper setup,
        # but we can trigger the broadcast function if we can call it.
        # Alternatively, we can just check if the broadcast contains the new fields.
        
        # Give some time for polling or manual triggers
        print("Waiting for broadcasts... (Press Ctrl+C to stop or wait 10s)")
        time.sleep(10)
        
        if received_updates:
            last_update = received_updates[-1]
            print("\nVerification Results:")
            print(f"Has full_commenter_list: {'full_commenter_list' in last_update}")
            print(f"Total comments: {last_update.get('total_comments')}")
            if 'full_commenter_list' in last_update:
                print(f"Full commenter list size: {len(last_update['full_commenter_list'])}")
        else:
            print("\nNo updates received. Make sure the server is running and polling.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        sio.disconnect()

if __name__ == "__main__":
    verify_realtime()
