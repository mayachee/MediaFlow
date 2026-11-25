"""Publish a folder of image Pins to one board using a signed-in Pinterest session."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://de.pinterest.com"
RUNS = ROOT / "runs"
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}


def plan():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--board", required=True)
    parser.add_argument("--link", required=True)
    parser.add_argument("--title", required=True, help="Title prefix. Each Pin also gets a number.")
    parser.add_argument("--description", default="")
    parser.add_argument("--create-board", action="store_true")
    parser.add_argument("--ai-generated", action="store_true")
    parser.add_argument("--publish", action="store_true", help="Publish the batch. Default is a preview.")
    args = parser.parse_args()
    destination = urlsplit(args.link)
    if destination.scheme not in {"http", "https"} or not destination.hostname:
        parser.error("--link must be an HTTP or HTTPS URL")
    if not args.images_dir.is_dir():
        parser.error(f"Image folder not found: {args.images_dir}")
    images = sorted(path for path in args.images_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_TYPES)
    if not images:
        parser.error("No images found")
    if not args.board.strip() or not args.title.strip():
        parser.error("Board and title must contain text")
    if len(args.title) + max(2, len(str(len(images)))) + 1 > 100:
        parser.error("Pin titles, including the sequence number, must fit in 100 characters")
    for path in images:
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            parser.error(f"Invalid image {path.name}: {exc}")
    return args, images


def find_board(page, name, create):
    from playwright.sync_api import TimeoutError

    page.goto(f"{BASE}/business/hub/", wait_until="domcontentloaded")
    profile = page.get_by_role("link", name="Your profile", exact=True)
    try:
        profile.wait_for(timeout=8000)
    except TimeoutError:
        page.goto(f"{BASE}/login/", wait_until="domcontentloaded")
        print("Sign in directly in the Pinterest window.", flush=True)
        profile.wait_for(timeout=240000)
    saved = urljoin(page.url, profile.get_attribute("href").rstrip("/") + "/_saved/")
    page.goto(saved, wait_until="domcontentloaded")
    button = page.get_by_role("button", name="Create a Pin or a board")
    button.wait_for(timeout=20000)
    board = page.get_by_role("link").filter(has=page.get_by_text(name, exact=True))
    if not board.count() and create:
        button.click()
        page.get_by_text("Board", exact=True).click()
        page.get_by_role("textbox", name="Name", exact=True).fill(name)
        page.get_by_role("button", name="Create", exact=True).last.click()
        done = page.get_by_role("button", name="Done", exact=True)
        try:
            done.click(timeout=5000)
        except TimeoutError:
            pass
        page.goto(saved, wait_until="domcontentloaded")
    if board.count() != 1:
        raise RuntimeError(f"Expected exactly one board named {name!r}")
    return urljoin(page.url, board.get_attribute("href"))


def board_pins(page, url):
    page.goto(url, wait_until="commit", timeout=25000)
    page.locator("#board-name").wait_for(state="attached", timeout=20000)
    page.wait_for_timeout(1800)
    links = page.locator('a[href*="/pin/"]').evaluate_all(
        r"els=>els.map(e=>e.getAttribute('href')).filter(h=>/^\/pin\/\d+\/?$/.test(h))")
    return {urljoin(page.url, link) for link in links}


def stage_pin(page, args, image, title):
    from playwright.sync_api import expect

    page.goto(f"{BASE}/pin-builder/", wait_until="commit", timeout=30000)
    page.locator('input[type=file][aria-label="File upload"]').first.set_input_files(str(image.resolve()))
    page.get_by_placeholder("Add your title").fill(title)
    if args.description:
        page.locator('[contenteditable=true][aria-label="Tell everyone what your Pin is about"]').fill(args.description)
    destination = page.get_by_placeholder("Add a destination link")
    destination.fill(args.link)
    expect(destination).to_have_value(args.link)
    cancel = page.get_by_role("button", name="Cancel", exact=True)
    if cancel.count() and cancel.first.is_visible():
        cancel.first.click(timeout=4000)
    selected = page.locator('[data-test-id="board-dropdown-item-selected"]')
    if selected.inner_text(timeout=10000).strip() != args.board:
        selected.click()
        page.get_by_text(args.board, exact=True).last.click()
    expect(selected).to_have_text(args.board)
    if args.ai_generated:
        page.locator('input[id^="pin-draft-ai-disclosure-"]:not([id$="-synthetic-performer"])').check(timeout=5000)


def save_receipt(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)


def publish(args, images):
    from playwright.sync_api import sync_playwright, TimeoutError

    RUNS.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(RUNS / "pinterest-artwork-browser"), channel="chrome", headless=False,
            viewport={"width": 1440, "height": 950})
        try:
            editor = context.pages[0]
            url = find_board(editor, args.board, args.create_board)
            key = hashlib.sha256(json.dumps(
                [url, str(args.images_dir.resolve()), args.link, args.title]
            ).encode()).hexdigest()[:16]
            receipt = RUNS / f"pinterest-batch-{key}.json"
            records = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
            board = context.new_page()
            for index, image in enumerate(images, 1):
                image_key = hashlib.sha256(image.read_bytes()).hexdigest()
                existing = records.get(image_key)
                if existing:
                    if not existing.get("url"):
                        raise RuntimeError(f"Check {existing['title']!r} on {url} before retrying. "
                                           f"Its outcome was uncertain. Receipt: {receipt}")
                    print(f"Already posted {image.name}: {existing['url']}", flush=True)
                    continue
                title = f"{args.title} {index:02d}"
                baseline = board_pins(board, url)
                stage_pin(editor, args, image, title)
                records[image_key] = {"title": title, "url": None}
                save_receipt(receipt, records)
                editor.get_by_text("Publish", exact=True).first.click(timeout=20000)
                for _ in range(7):
                    try:
                        new = board_pins(board, url) - baseline
                    except TimeoutError:
                        continue
                    if len(new) == 1:
                        candidate = new.pop()
                        board.goto(candidate, wait_until="commit", timeout=25000)
                        try:
                            board.get_by_text(title, exact=True).first.wait_for(timeout=12000)
                        except TimeoutError:
                            continue
                        records[image_key]["url"] = candidate
                        save_receipt(receipt, records)
                        print(f"Posted {index}/{len(images)}: {candidate}", flush=True)
                        break
                else:
                    raise RuntimeError(f"Could not confirm {title!r}. Check {url} before retrying.")
        finally:
            context.close()


def main():
    args, images = plan()
    print(f"Board: {args.board}\nLink: {args.link}\nImages: {len(images)}", flush=True)
    if args.publish:
        try:
            publish(args, images)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        for index, image in enumerate(images, 1):
            print(f"{args.title} {index:02d} | {image.name}")


if __name__ == "__main__":
    main()
