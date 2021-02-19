import html
import json
import logging
import queue
import random
import re
import threading
import time
import urllib.parse
from pathlib import Path


import click
import requests
from requests import cookies
from requests.models import cookiejar_from_dict
import selenium.webdriver as webdriver
import selenium.webdriver.chrome.options as chrome_options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.touch_actions import TouchActions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s:%(threadName)s:%(message)s",
)

# WebDriverWait timeout in seconds.
WAIT_TIMEOUT = 10

# Queue for processing scraped photos.
photo_queue = queue.SimpleQueue()


class Sentinel:
    """Indicates no more items in queue."""

    pass


@click.command()
@click.argument("username")
@click.argument("password", envvar="FB_PASSWORD")
@click.argument("directory", type=click.Path(exists=True))
@click.option(
    "--wait",
    default=True,
    type=bool,
    help="Wait a random amount of time between requests",
)
def photos_of_me(username, password, directory, wait):
    """Download "photos of me" to DIRECTORY, using Facebook credentials
    USERNAME and PASSWORD.

    DON'T supply your PASSWORD as a command line argument! Set the FB_PASSWORD
    environment variable instead:

        read -s FB_PASSWORD

        (Type your password, and then press <ENTER>.)

        python photos-of-me.py me@mydomain.com $FB_PASSWORD
    """
    # Create photo processing thread.
    thread = threading.Thread(target=process_photo_queue, args=(directory, wait))
    # Prep the browser.
    driver = chrome_driver()
    sign_in_to_facebook(driver, username, password)
    go_to_first_photo(driver)
    try:
        thread.start()
        # Start scraping.
        for photo in photos(driver, wait):
            photo_queue.put(photo)
            logging.info("Put photo in queue")
            # Uncomment the next line to break after first photo.
            # break
        photo_queue.put(Sentinel)
    except KeyboardInterrupt:
        photo_queue.put(Sentinel)
    thread.join()


def chrome_driver():
    """Returns instance of Chrome webdriver."""
    options = chrome_options.Options()
    options.add_experimental_option("w3c", False)
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def sign_in_to_facebook(driver, username, password):
    """Signs in to Facebook with `username` and `password`."""
    driver.get("https://m.facebook.com/")
    driver.find_element_by_css_selector("input[name='email']").send_keys(username)
    driver.find_element_by_css_selector("input[name='pass']").send_keys(password)
    driver.find_element_by_css_selector("button[name='login']").click()
    # Wait until title changes.
    title = driver.title
    Wait(driver, timeout=WAIT_TIMEOUT).until_not(EC.title_is(title))
    # Then just go here again to skip that "one tap login" bullshit.
    driver.get("https://m.facebook.com/")
    logging.info("Signed in to Bookface")


def go_to_first_photo(driver):
    """Navigates to first photo of you."""
    wait = Wait(driver, timeout=WAIT_TIMEOUT)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.profpic"))).click()
    wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.scrollAreaBody > a"))
    ).click()
    wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.timeline.photos > span > a"))
    ).click()
    logging.info("Arrived at first photo of you")


def get_photo(driver):
    """Scrapes photo details from page."""
    return {
        "actor": driver.find_element_by_css_selector("strong.actor").text,
        "url": driver.find_element_by_link_text("View full size").get_attribute("href"),
        "caption": driver.find_element_by_xpath(
            "//div[@id='voice_replace_id']/.."
        ).text,
        "date": driver.find_element_by_css_selector("abbr").text,
        # We need cookies for authenticate requests ;)
        "cookies": driver.get_cookies(),
    }


def tap_next_photo(driver):
    """Taps next photo button."""
    TouchActions(driver).tap(
        driver.find_element_by_xpath(
            "//a[@data-sigil='touchable']/span[text()='Next']/.."
        )
    ).perform()
    logging.info("Tapped on next photo")


def photos(driver, wait):
    """Generates photo details.

    Wait a random amount of time between requests if `wait` is True.
    """
    # Loop until there is no "Next" button to click --  I assume this would
    # mean the end of photos.
    while True:
        if wait:
            time.sleep(random.random() + 0.3)
        try:
            # Wait for "View full size" link.
            Wait(driver, timeout=WAIT_TIMEOUT).until(
                EC.element_to_be_clickable(
                    (
                        By.LINK_TEXT,
                        "View full size",
                    )
                )
            )
            photo = get_photo(driver)
            logging.debug(photo)
            yield photo
        except TimeoutException:
            logging.warning('"View full size" link did not appear')
        try:
            tap_next_photo(driver)
        except NoSuchElementException:
            logging.info("Can't find a next photo to tap")
            break


def process_photo_queue(directory, wait: bool):
    """Write photos in queue to `directory."""
    logging.info("Photo processing thread started")
    while True:
        if wait:
            time.sleep(random.random() + 0.3)
        photo = photo_queue.get()
        if photo is Sentinel:
            break
        process(photo, directory)
        logging.debug("Processed %s", photo)
    logging.info("Photo processing complete")


def get_redirect_url(url: str, cookies: list) -> str:
    """Returns redirect URL from URL.

    The "View full size" URL redirects to the *real* image.
    """
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(name=cookie["name"], value=cookie["value"])
    text = session.get(url).text
    try:
        return html.unescape(re.search(pattern=r';url=(.+?)"', string=text).group(1))
    except AttributeError:
        logging.error("Couldn't match redirect URL in %s", text)
        raise


def process(photo: dict, directory: str):
    """Write photo to directory, with metadata."""
    try:
        # Get the REAL photo URL!
        photo_url = get_redirect_url(photo["url"], photo["cookies"])
    except AttributeError:
        # Not much we can do, move on.
        return
    # We extract a suitable photo filename from the URL.
    filename = Path(urllib.parse.urlparse(photo_url).path).name
    # Write photo to file.
    photo_path = Path(directory) / filename
    with photo_path.open(mode="wb") as file:
        file.write(requests.get(photo_url).content)
    logging.info("Wrote photo to %s", photo_path)
    # Write photo information to file (JSON).
    json_path = Path(directory) / (filename + ".json")
    with json_path.open(mode="w") as file:
        file.write(json.dumps(photo, indent=2))
    logging.info("Wrote photo information to %s", json_path)


if __name__ == "__main__":
    photos_of_me()
