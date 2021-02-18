import logging

import argparse, os, time, wget, json, piexif, ssl, urllib
import selenium.webdriver as webdriver
import selenium.webdriver.chrome.options as chrome_options
from selenium.common.exceptions import NoSuchElementException
from dateutil.parser import parse
from datetime import datetime
from datetime import timedelta


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def configure_driver():
    """Returns instance of Chrome webdriver."""
    options = chrome_options.Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def sign_in_to_facebook(driver, username, password):
    """Signs in to Facebook with `username` and `password`."""
    logger.info("Signing in to Bookface")
    driver.get("https://mbasic.facebook.com/")
    driver.find_element_by_id("m_login_email").send_keys(username)
    driver.find_element_by_css_selector('input[type="password"]').send_keys(password)
    driver.find_element_by_css_selector('input[name="login"]').click()
    try:
        # Skip "Log in with one tap" page.
        if driver.find_element_by_css_selector("h3.o").text == "Log in with one tap":
            logger.info("No, I don't want to log in with one tap 🚰")
            driver.find_element_by_css_selector('a[href^="/login"]').click()
    except NoSuchElementException:
        logging.info('Did not encounter "Log in with one tap" page')
        pass


def go_to_first_photo(driver):
    """Navigates to first photo of you."""
    logger.info("Clicking through to first photo in 'photos of you'")
    driver.find_element_by_css_selector('a[href^="/menu"]').click()
    driver.find_element_by_link_text("Photos").click()
    driver.find_element_by_css_selector("a.cn.co.cp").click()


def get_photo(driver):
    """Scrapes photo details from page."""
    return {
        "actor": driver.find_element_by_css_selector("strong.actor").text,
        "url": driver.find_element_by_link_text("View full size").get_attribute("href"),
        "caption": driver.find_element_by_xpath(
            "//div[@id='voice_replace_id']/.."
        ).text,
        "date": driver.find_element_by_css_selector("abbr").text,
    }


def photos(driver):
    """Generates photo details."""
    # Loop until there is no "Next" link to click.
    try:
        while True:
            photo = get_photo(driver)
            logging.debug(photo)
            yield photo
            logging.info("Going to next photo")
            driver.find_element_by_css_selector("td.w > a").click()
    except NoSuchElementException:
        logging.info("Reached the last photo, or some other page")
        pass


def download_photos():
    ssl._create_default_https_context = ssl._create_unverified_context
    # Prep the download folder
    folder = "photos/"
    if not os.path.exists(folder):
        os.makedirs(folder)
    print("Saving photos to " + folder)
    # Download the photos
    with open("tagged.json") as json_file:
        data = json.load(json_file)
        for i, d in enumerate(data["tagged"]):
            if d["media_type"] == "image":
                # Save new file
                if d["fb_date"] == "Today":
                    filename_date = datetime.today().strftime("%Y-%m-%d")
                elif d["fb_date"] == "Yesterday":
                    filename_date = datetime.today() - timedelta(days=1)
                    filename_date = filename_date.strftime("%Y-%m-%d")
                else:
                    filename_date = parse(d["fb_date"]).strftime("%Y-%m-%d")
                img_id = d["media_url"].split("_")[1]
                new_filename = folder + filename_date + "_" + img_id + ".jpg"
                if os.path.exists(new_filename):
                    print("Already Exists (Skipping): %s" % (new_filename))
                else:
                    delay = 1

                    while True:
                        try:
                            print("Downloading " + d["media_url"])
                            img_file = wget.download(
                                d["media_url"], new_filename, False
                            )
                            break
                        except (TimeoutError, urllib.error.URLError) as e:
                            print("Sleeping for {} seconds".format(delay))
                            time.sleep(delay)
                            delay *= 2
                    # Update EXIF Date Created
                    exif_dict = piexif.load(img_file)
                    if d["fb_date"] == "Today":
                        exif_date = datetime.today().strftime("%Y:%m:%d %H:%M:%S")
                    elif d["fb_date"] == "Yesterday":
                        exif_date = datetime.today() - timedelta(days=1)
                        exif_date = exif_date.strftime("%Y:%m:%d %H:%M:%S")
                    else:
                        exif_date = parse(d["fb_date"]).strftime("%Y:%m:%d %H:%M:%S")
                    img_desc = (
                        d["fb_caption"]
                        + "\n"
                        + d["fb_tags"]
                        + "\n"
                        + d["fb_url"].split("&")[0]
                    )
                    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date
                    exif_dict["0th"][piexif.ImageIFD.Copyright] = (
                        d["user_name"] + " (" + d["user_url"]
                    ) + ")"
                    exif_dict["0th"][
                        piexif.ImageIFD.ImageDescription
                    ] = img_desc.encode("utf-8")

                    piexif.insert(piexif.dump(exif_dict), img_file)
                    print(str(i + 1) + ") Added " + new_filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Facebook Scraper")
    parser.add_argument("-u", type=str, help="FB Username")
    parser.add_argument("-p", type=str, help="FB Password")
    parser.add_argument("--download", action="store_true", help="Download photos only")
    parser.add_argument("--index", action="store_true", help="Index photos")
    args = parser.parse_args()
    try:
        if args.download:
            download_photos()
        else:
            if not (args.u and args.p):
                print("Please try again with FB credentials (use -u -p)")
            else:
                driver = configure_driver()
                sign_in_to_facebook(driver, args.u, args.p)
                go_to_first_photo(driver)
                for photo in photos(driver):
                    print(photo)
    except KeyboardInterrupt:
        print(
            "\nThanks for using the script! Please raise any issues at: https://github.com/jcontini/fb-photo-downloader/issues/new"
        )
        pass
