import os
import sys
import pickle
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Google API scopes for YouTube upload
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_authenticated_service():
    creds = None
    token_file = "token.pickle"
    client_secret_file = "client_secret.json"
    
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing token...", flush=True)
            creds.refresh(Request())
        else:
            print("Starting browser auth...", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)
    
    return build("youtube", "v3", credentials=creds)

def upload_video(youtube, video_path, title, description, tags, privacy="public"):
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "10",  # Music
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    
    print("Preparing upload...", flush=True)
    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )
    
    print("Uploading...", flush=True)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%", flush=True)
    
    print(f"Video uploaded successfully! Video ID: {response['id']}", flush=True)
    return response["id"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--privacy", default="public", choices=["public", "private", "unlisted"])
    args = parser.parse_args()
    
    print("Authenticating...", flush=True)
    youtube = get_authenticated_service()
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    
    upload_video(
        youtube,
        args.video,
        args.title,
        args.description,
        tags,
        args.privacy,
    )

if __name__ == "__main__":
    main()