import html
import logging
import queue
import random
import re
import threading
import time
import urllib.parse
from pathlib import Path
from typing import List, NamedTuple
import traceback

import click
import dateutil.parser
import exif
import requests
import selenium.webdriver as webdriver
import selenium.webdriver.chrome.options as chrome_options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s:%(levelname)s:%(name)s:%(threadName)s:%(message)s",
)

# WebDriverWait timeout in seconds.
WAIT_TIMEOUT = 100

# Queue of URLs to photo pages.
photo_page_queue = queue.SimpleQueue()


class Sentinel(object):
    """Indicates no more items in queue."""

    pass


@click.command()
@click.argument("username")
@click.argument("password", envvar="FB_PASSWORD")
@click.argument("tfa_code", envvar="FB_TFA_CODE")
@click.argument("directory", type=click.Path(exists=True))
@click.option(
    "--workers",
    type=int,
    default=1,
    help="Number of concurrent worker threads (default is 1).",
)
@click.option(
    "--wait/--no-wait",
    default=True,
    help="Wait a brief random amount of time between requests (default is wait).",
)
@click.option(
    "--offset",
    default=0,
    type=int,
    help="Initial photo offset (default is 0).",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set the logging level (default is INFO).",
)
@click.option(
    "--detach/--no-detach",
    default=False,
    help="Detach the Chrome browser (default is no detach).",
)
def photos_of_me(username, password, tfa_code, directory, workers: int, wait: bool, offset: int, detach: bool, log_level: str):
    """Download "photos of me" to DIRECTORY, using Facebook credentials
    USERNAME and PASSWORD, and temporary TFA_CODE

    Instead of supplying PASSWORD on the command line, you can set the FB_PASSWORD
    environment variable:

        read -s FB_PASSWORD

        (Type your password, and then press <ENTER>.)
    
    USAGE

        photos-of-me.py [OPTIONS] USERNAME PASSWORD TFA_CODE DIRECTORY
    """
    logging.getLogger().setLevel(log_level)
    driver = chrome_driver(detach)
    sign_in_to_facebook(driver, username, password, tfa_code)
    cookies = driver.get_cookies()
    # Create worker threads to process photo URLs.
    photo_page_queue_workers = [
        threading.Thread(
            target=process_photo_page_queue,
            args=(cookies, directory, wait, detach),
            daemon=True,
        )
        for _ in range(workers)
    ]
    # Start the workers.
    for worker in photo_page_queue_workers:
        worker.start()
    go_to_photos_of_you(driver)
    # This is the URL of the first page of "photos of you".
    first_photos_of_you_page = driver.current_url
    # You can get to all "photos of you" pages by setting the offset query parameter.
    photos_of_you_url = get_offset_photos_of_you_page(first_photos_of_you_page, offset)
    photo_urls = get_photo_urls(driver, photos_of_you_url)
    # Keep increasing offset until we reach a page with no photos.
    while photo_urls:
        if wait:
            time.sleep(random.random() + 0.2)
        for url in photo_urls:
            photo_page_queue.put(url)
        offset = offset + 12
        photos_of_you_url = get_offset_photos_of_you_page(
            first_photos_of_you_page, offset
        )
        photo_urls = get_photo_urls(driver, photos_of_you_url)
    photo_page_queue.put(Sentinel)
    driver.close()
    for worker in photo_page_queue_workers:
        worker.join()


def chrome_driver(detach: bool) -> webdriver.Chrome:
    """Returns instance of Chrome webdriver."""
    options = chrome_options.Options()
    if detach:
        options.add_experimental_option("detach", True)
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")
    return webdriver.Chrome(options=options)


def get_offset_photos_of_you_page(first_page_url: str, offset: int) -> str:
    """Returns a URL to a "photos of you page", offset by `offset`."""
    # Parse URL into its components.
    url_components = urllib.parse.urlparse(first_page_url)
    # Parse URL query component.
    query = urllib.parse.parse_qs(url_components.query)
    # You can get to any "photos of you" pages by setting the offset query parameter.
    query["offset"] = [str(offset)]
    # Construct a new URL with a modified offset query component.
    return urllib.parse.urlunparse(
        url_components._replace(query=urllib.parse.urlencode(query, doseq=True))
    )


def sign_in_to_facebook(driver: webdriver.Chrome, username: str, password: str, tfa_code: str) -> None:
    """Signs in to Facebook with `username` and `password`."""
    driver.get("https://mbasic.facebook.com/")
    try:
        accept_button = driver.find_element(By.CSS_SELECTOR, "button[name='accept_only_essential']")
        accept_button.click()
    except NoSuchElementException:
        pass
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is('test'))
    driver.find_element(By.CSS_SELECTOR, "input[name='email']").send_keys(username)
    driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(password)
    title = driver.title
    driver.find_element(By.CSS_SELECTOR, "input[name='login']").click()
    # Wait until title changes.
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))

    # Start the flow with 2FA codes, can omit if not using

    # 2FA page
    title = driver.title
    driver.find_element(By.CSS_SELECTOR, "input[name='approvals_code']").send_keys(tfa_code)
    driver.find_element(By.CSS_SELECTOR, "input[name='submit[Submit Code]']").click()
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))

    # Save browser page
    driver.find_element(By.CSS_SELECTOR, "input[name='submit[Continue]']").click()
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))
    
    # These pop-up sometimes, not sure exactly when, so optionally traverse them
    try:
        # Review login page
        driver.find_element(By.CSS_SELECTOR, "input[name='submit[Continue]']").click()
        Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))
        
        # Review login page
        driver.find_element(By.CSS_SELECTOR, "input[name='submit[This was me]']").click()
        Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))

        # 2nd Review login page
        driver.find_element(By.CSS_SELECTOR, "input[name='submit[Continue]']").click()
        Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))
    except:
        print("not sure about that 2nd review page")

    # end 2FA flow

    # Just go here again to skip that "one tap login" bullshit.
    driver.get("https://mbasic.facebook.com/")
    logging.info("Signed in to Bookface")


def go_to_photos_of_you(driver: webdriver.Chrome) -> None:
    """Navigates to first page of "photos of you"."""
    # Go to "Menu".
    driver.get("https://mbasic.facebook.com/menu/bookmarks/")
    # Click "Photos" link.
    driver.find_element(By.XPATH, "//a[contains(@href, '/photos')]").click()
    # Click "See All (XXX)" link.
    driver.find_element(By.CSS_SELECTOR, 
        "div:not([title='Uploads']) > section > a"
    ).click()
    logging.info("Arrived at first page of photos of you")


def get_photo_urls(driver: webdriver.Chrome, url: str) -> List[str]:
    """Return photo URLs from `url`.

    `url` is a "photos of you" page.
    """
    driver.get(url)
    urls = [
        element.get_attribute("href")
        for element in driver.find_elements(By.CSS_SELECTOR, "td.s > div > a")
    ]
    logging.info("Scraped %s photo urls from %s", len(urls), driver.current_url)
    return urls


class Media(NamedTuple):
    type: str
    actor: str
    caption: str
    date: str
    full_size_url: str
    cookies: list


def get_media_details(driver: webdriver.Chrome, url: str) -> Media:
    """Returns media details from photo page `url`.

    Can be a photo or video.
    """
    driver.get(url)
    fbid = parse_qs(urlparse(url).query).get("fbid", [None])[0]
    og_type = driver.find_element(By.CSS_SELECTOR, 
        'head > meta[property="og:type"]'
    ).get_attribute("content")
    if not og_type.startswith("video"):
        return Media(
            type="photo",
            actor=driver.find_element(By.CSS_SELECTOR, "a > strong").text,
            caption=driver.find_element(By.CSS_SELECTOR, "div.msg > div").text
            + "\nDownloaded from Facebook fbid={}".format(fbid),
            date=driver.find_element(By.CSS_SELECTOR, "abbr").text,
            # Is this getting full size? We could follow 'head > link[p="canonical"]' and download from there?
            full_size_url=driver.find_element(By.CSS_SELECTOR, 
                'head > meta[property="og:image"]'
            ).get_attribute("content"),
            # We need cookies for authenticated requests ;)
            cookies=driver.get_cookies(),
        )
    else:
        # Video export broken as of 2024-02-11
        return Media(
            type="video",
            actor=driver.find_element(By.CSS_SELECTOR, "strong > a").text,
            caption=driver.find_element(By.CSS_SELECTOR, 
                "div> a[aria-label]"
            ).get_attribute("aria-label"),
            date=driver.find_element(By.CSS_SELECTOR, "abbr").text,
            full_size_url=driver.find_element(By.CSS_SELECTOR, 
                "div> a[aria-label]"
            ).get_attribute("href"),
            # We need cookies for authenticated requests ;)
            cookies=driver.get_cookies(),
        )


def process_photo_page_queue(cookies: list, directory: str, wait: bool, detach: bool):
    """Processes pages in photo page queue.

    - Spawn a Selenium webdriver
    - Sign in to Facebook (using `cookies`)
    - Process pages in queue:
        - Get media details
        - Download media
        - Write EXIF data to photo, if photo
        - Write media to `directory`

    Wait a random amount of time between queue items if `wait` is True.
    """
    driver = chrome_driver(detach)
    # First, go to a domain that cookies apply to.
    driver.get("https://mbasic.facebook.com/")
    for cookie in cookies:
        driver.add_cookie(cookie)
    while True:
        if wait:
            time.sleep(random.random() + 0.2)
        page = photo_page_queue.get()
        if page is Sentinel:
            photo_page_queue.put(Sentinel)
            logging.info("Reached end of queue")
            break
        try:
            media = get_media_details(driver, page)
        except NoSuchElementException:
            # This is raised if a photo page doesn't contain media details.
            # Ignore, and move on to next item in queue.
            logging.error(
                "Error scraping details from photo page %s: %s",
                page,
                traceback.format_exc(),
            )
            continue
        if media.type == "photo":
            try:
                download_photo(media, directory)
            except RuntimeError:
                # This is raised if a URL can't be parsed from a photo redirect page.
                # Ignore, and move on to next item in queue.
                pass
        elif media.type == "video":
            download_video(media, directory=directory)
            logging.info("Processed %s", page)


def download_photo(photo: Media, directory: str) -> None:
    """Downloads `photo` to `directory`."""
    # Get the REAL photo URL!
    # url = get_photo_url(photo.full_size_url, photo.cookies)
    url = photo.full_size_url
    # Extract a suitable media filename from the URL.
    filename = Path(urllib.parse.urlparse(url).path).name
    photo_path = Path(directory) / filename
    # If photo does not already exist, write with EXIF data.
    if not photo_path.exists():
        photo_content = requests.get(url).content
        photo_path.open(mode="wb").write(
            with_exif_data(
                photo=photo_content,
                actor=photo.actor,
                caption=photo.caption,
                date=photo.date,
            )
        )
        logging.info("Wrote photo to %s", photo_path)
    else:
        logging.info("Photo already exists, skipping (%s)", photo_path)


def download_video(video: Media, directory: str) -> None:
    """Downloads `video` to `directory`."""
    session = requests.Session()
    for cookie in video.cookies:
        session.cookies.set(name=cookie["name"], value=cookie["value"])
    response = session.get(video.full_size_url)
    # Extract a suitable media filename from the URL.
    filename = Path(urllib.parse.urlparse(response.url).path).name
    video_path = Path(directory) / filename
    # Write if video does not already exist.
    if not video_path.exists():
        video_path.open(mode="wb").write(response.content)
        logging.info("Wrote video to %s", video_path)
    else:
        logging.info("Video already exists, skipping (%s)", video_path)


def get_photo_url(full_size_url: str, cookies: list) -> str:
    """Returns redirect URL from `full_size_url`.

    The "View Full Size" URL redirects to the *real* image.
    """
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(name=cookie["name"], value=cookie["value"])
    text = session.get(full_size_url).text
    try:
        return html.unescape(re.search(pattern=r';url=(.+?)"', string=text).group(1))
    except AttributeError:
        logging.error("Couldn't match redirect URL in %s", text)
        raise RuntimeError(f"Couldn't match redirect URL in {text}")


def with_exif_data(photo: bytes, actor: str, caption: str, date: str) -> bytes:
    """Returns photo with EXIF data."""
    image = exif.Image(photo)
    if actor:
        # Replace any non-ASCII characters.
        image["artist"] = actor.encode(encoding="ascii", errors="replace").decode()
    if date:
        image["datetime_original"] = dateutil.parser.parse(date).strftime(
            exif.DATETIME_STR_FORMAT
        )
    if caption:
        # Replace any non-ASCII characters. Apparently user_comment should be
        # able to support arbitrary data. But that doesn't seem to work with
        # the exif package.
        image["user_comment"] = caption.encode(
            encoding="ascii", errors="replace"
        ).decode()
    return image.get_file()


if __name__ == "__main__":
    photos_of_me()
