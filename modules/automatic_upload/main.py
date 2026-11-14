from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import quote


def main():
    # Read songs from input.txt
    with open("input.txt", "r", encoding="utf-8") as f:
        songs = [line.strip() for line in f if line.strip()]

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        # Give pages more time to load
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(60000)

        for song in songs:
            print(f"\nSearching: {song}")

            try:
                # Directly open YouTube search
                search_url = (
                    "https://www.youtube.com/results?search_query="
                    + quote(song)
                )

                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                # Wait for YouTube search results
                first_video = page.locator(
                    "ytd-video-renderer a#video-title"
                ).first

                first_video.wait_for(
                    state="visible",
                    timeout=15000
                )

                url = first_video.get_attribute("href")

                if url:
                    if url.startswith("/"):
                        url = "https://www.youtube.com" + url

                    results.append(url)

                    print(f"Found: {url}")
                else:
                    print("No URL found.")

            except PlaywrightTimeoutError:
                print(f"Timeout while searching: {song}")
                continue

            except Exception as e:
                print(f"Error with '{song}': {e}")
                continue

        browser.close()

    # Save results
    with open("youtube_links.txt", "w", encoding="utf-8") as f:
        for url in results:
            f.write(url + "\n")

    print("\n--------------------------------")
    print(f"Finished. Found {len(results)} videos.")
    print("Saved to youtube_links.txt")
    print("--------------------------------")


if __name__ == "__main__":
    main()