# photos-of-me

This repository was forked from https://github.com/jcontini/facebook-photos-download.

This tool allows you to download all "photos of you" from Facebook (and videos too!). Photos are populated with EXIF data to preserve dates, captions and uploader name.


## Installation

Get the following:

- Python 3.8+
- [Poetry](https://python-poetry.org)
- [chromedriver](http://chromedriver.chromium.org/downloads) available on `PATH`

Then do the following:

1. Clone this repository
2. `cd` into the cloned folder
3. Run `poetry install`


## Usage

```
Usage: photos-of-me.py [OPTIONS] USERNAME PASSWORD DIRECTORY

  Download "photos of me" to DIRECTORY, using Facebook credentials USERNAME
  and PASSWORD.

  Instead of supplying PASSWORD on the command line, you can set the
  FB_PASSWORD environment variable:

      read -s FB_PASSWORD

      (Type your password, and then press <ENTER>.)

      python photos-of-me.py me@mydomain.com $FB_PASSWORD photos

Options:
  --workers INTEGER   Number of concurrent worker threads (default is 1).
  --wait / --no-wait  Wait a brief random amount of time between requests
                      (default is wait).

  --offset INTEGER    Initial photo offset (default is 0).
  --help              Show this message and exit.
```
