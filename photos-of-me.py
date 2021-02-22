import html
import logging
import queue
import random
import re
import threading
import time
import urllib.parse
from pathlib import Path
from typing import List


import click
import dateutil.parser
import exif
import requests
import selenium.webdriver as webdriver
import selenium.webdriver.chrome.options as chrome_options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s:%(threadName)s:%(message)s",
)

# WebDriverWait timeout in seconds.
WAIT_TIMEOUT = 10

# Queue of URLs to photo pages.
photo_page_queue = queue.Queue()


@click.command()
@click.argument("username")
@click.argument("password", envvar="FB_PASSWORD")
@click.argument("directory", type=click.Path(exists=True))
@click.option(
    "--workers", type=int, default=1, help="Number of concurrent worker threads"
)
@click.option(
    "--dont-wait",
    default=False,
    type=bool,
    help="Don't wait a brief random amount of time between requests",
)
def photos_of_me(username, password, directory, workers: int, dont_wait: bool):
    """Download "photos of me" to DIRECTORY, using Facebook credentials
    USERNAME and PASSWORD.

    DON'T supply your PASSWORD as a command line argument! Set the FB_PASSWORD
    environment variable instead:

        read -s FB_PASSWORD

        (Type your password, and then press <ENTER>.)

        python photos-of-me.py me@mydomain.com $FB_PASSWORD
    """
    # Create worker threads to process photo URLs.
    photo_page_queue_workers = [
        threading.Thread(
            target=process_photo_page_queue,
            args=(username, password, directory, dont_wait),
        )
        for _ in range(workers)
    ]
    # Prep the browser.
    driver = chrome_driver()
    # This is the URL of the first page of "photos of you".
    first_photos_of_you_page = get_first_photos_of_you_page(driver, username, password)
    # Start the workers.
    for worker in photo_page_queue_workers:
        worker.start()
    # You can get to all "photos of you" pages by setting the offset query parameter.
    # We start with an offset of 0.
    offset = 0
    photos_of_you_url = get_offset_photos_of_you_page(first_photos_of_you_page, offset)
    photo_urls = get_photo_urls(driver, photos_of_you_url)
    # Keep increasing offset until we reach a page with no photos.
    while photo_urls:
        if not dont_wait:
            time.sleep(random.random() + 0.2)
        for url in photo_urls:
            photo_page_queue.put(url)
        offset = offset + 12
        photos_of_you_url = get_offset_photos_of_you_page(
            first_photos_of_you_page, offset
        )
        photo_urls = get_photo_urls(driver, photos_of_you_url)
    photo_page_queue.join()


def chrome_driver() -> webdriver.Chrome:
    """Returns instance of Chrome webdriver."""
    options = chrome_options.Options()
    options.add_experimental_option("w3c", False)
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")
    return webdriver.Chrome(options=options)


def get_first_photos_of_you_page(
    driver: webdriver.Chrome, username: str, password: str
) -> str:
    """Returns URL of first "photos of you" page."""
    sign_in_to_facebook(driver, username, password)
    go_to_photos_of_you(driver)
    return driver.current_url


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


def sign_in_to_facebook(driver: webdriver.Chrome, username: str, password: str) -> None:
    """Signs in to Facebook with `username` and `password`."""
    driver.get("https://mbasic.facebook.com/")
    title = driver.title
    driver.find_element_by_css_selector("input[name='email']").send_keys(username)
    driver.find_element_by_css_selector("input[name='pass']").send_keys(password)
    driver.find_element_by_css_selector("input[name='login']").click()
    # Wait until title changes.
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))
    # Then just go here again to skip that "one tap login" bullshit.
    driver.get("https://mbasic.facebook.com/")
    logging.info("Signed in to Bookface")


def go_to_photos_of_you(driver: webdriver.Chrome) -> None:
    """Navigates to first page of "photos of you"."""
    # Click "Menu" link.
    driver.find_element_by_css_selector("a[accesskey='5']").click()
    # Click "Photos" link.
    driver.find_element_by_css_selector("div.bq > div:nth-child(2) > a").click()
    # Click "See All (XXX)" link.
    driver.find_element_by_css_selector(
        "div:not([title='Uploads']) > section.ct > a"
    ).click()
    logging.info("Arrived at first page of photos of you")


def get_photo_urls(driver: webdriver.Chrome, url: str) -> List[str]:
    """Return photo URLs from `url`.

    `url` is a "photos of you" page.
    """
    driver.get(url)
    urls = [
        element.get_attribute("href")
        for element in driver.find_elements_by_css_selector("td.s > div > a")
    ]
    logging.info("Scraped %s photo urls from %s", len(urls), driver.current_url)
    return urls


def get_photo_details(driver: webdriver.Chrome, url: str) -> dict:
    """Returns photo details from photo page `url`."""
    driver.get(url)
    return {
        "actor": driver.find_element_by_css_selector("strong.actor").text,
        "caption": driver.find_element_by_xpath(
            "//div[@id='voice_replace_id']/.."
        ).text,
        "date": driver.find_element_by_css_selector("abbr").text,
        "full_size_url": driver.find_element_by_link_text(
            "View full size"
        ).get_attribute("href"),
        # We need cookies for authenticated requests ;)
        "cookies": driver.get_cookies(),
    }


def process_photo_page_queue(
    username: str, password: str, directory: str, dont_wait: bool
):
    """Processes pages in photo page queue.

    - Spawn a Selenium webdriver
    - Sign in to Facebook (using `username` and `password`)
    - Process pages in queue:
        - Get photo details
        - Write photo to `directory`
        - Write EXIF data to photo

    Wait a random amount of time between queue items if `dont_wait` is not True.
    """
    driver = chrome_driver()
    sign_in_to_facebook(driver, username, password)
    while True:
        if not dont_wait:
            time.sleep(random.random() + 0.2)
        page = photo_page_queue.get()
        try:
            details = get_photo_details(driver, page)
            # Get the REAL photo URL!
            photo_url = get_photo_url(details["full_size_url"], details["cookies"])
            # Extract a suitable photo filename from the URL.
            filename = Path(urllib.parse.urlparse(photo_url).path).name
            photo_path = Path(directory) / filename
            # If photo does not already exist, write with EXIF data.
            if not photo_path.exists():
                photo = requests.get(photo_url).content
                photo_path.open(mode="wb").write(
                    with_exif_data(
                        photo, details["actor"], details["caption"], details["date"]
                    )
                )
            else:
                logging.info("Photo already exists, skipping (%s)", photo_path)
        except NoSuchElementException:
            # This is raised if a photo page doesn't contain photo details.
            # Ignore, and move on to next item in queue.
            logging.error("Error scraping details from photo page %s", page)
            pass
        except RuntimeError:
            # This is raised if a URL can't be parsed from a photo redirect page.
            # Ignore, and move on to next item in queue.
            pass
        photo_page_queue.task_done()
        logging.info("Processed %s", page)


def get_photo_url(full_size_url: str, cookies: list) -> str:
    """Returns redirect URL from `full_size_url`.

    The "View full size" URL redirects to the *real* image.
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
