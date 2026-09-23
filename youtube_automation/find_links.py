import yt_dlp

ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
for query in ["Please Please Please Sabrina Carpenter", "undressed sombr"]:
    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
    if "entries" in info:
        e = info["entries"][0]
        print(f"{query}: https://www.youtube.com/watch?v={e['id']}")
