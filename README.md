# photos-of-me

This repository was forked from https://github.com/jcontini/facebook-photos-download.

This tool allows you to download all your "photos of you" from Facebook. Photos are populated with EXIF data to preserve dates, captions and uploader name.


## Installation

You'll need

- Python 3.8
- [Poetry](https://python-poetry.org)
- [chromedriver](http://chromedriver.chromium.org/downloads) available on `PATH`

Once you have the above

1. Clone this repository
2. `cd` into the cloned folder
3. Run `poetry install`


## Usage

```
Usage: photos-of-me.py [OPTIONS] USERNAME PASSWORD DIRECTORY

  Download "photos of me" to DIRECTORY, using Facebook credentials USERNAME
  and PASSWORD.

  DON'T supply your PASSWORD as a command line argument! Set the FB_PASSWORD
  environment variable instead:

      read -s FB_PASSWORD

      (Type your password, and then press <ENTER>.)

      python photos-of-me.py me@mydomain.com $FB_PASSWORD

Options:
  --workers INTEGER    Number of concurrent worker threads
  --dont-wait BOOLEAN  Don't wait a brief random amount of time between
                       requests

  --help               Show this message and exit.
```
