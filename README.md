# photos-of-me

This repository has been forked twice, originally from https://github.com/jcontini/facebook-photos-download, and then from an updated fork of that, https://github.com/eidorb/photos-of-me. And now, third time. 

This was working with 2FA enabled on my account, as of April 2023. Occasionally errors occur, where Facebook may throw a browser error and therefore parsing stops. You can note the last working offset number and try again, resuming from that spot later. This may be due to rate limiting or other bot detection.

This tool allows you to download all "photos of you" from Facebook (and videos too!). Photos are populated with EXIF data to preserve dates, captions and uploader name.

### What's different
- GDPR support (decline cookies)
- dependencies updated
- deprecated webdriver functions fixed
- chromedriver is installed via poetry
- quickstart setup.sh script
- webdriver detach mode for debug
- some selector fixes

## Installation

Get the following:

- Python 3.8+
- [Poetry](https://python-poetry.org)
- [chromedriver](http://chromedriver.chromium.org/downloads) available on `PATH`
- Chromium or Chrome

Then do the following:

1. Clone this repository
2. `cd` into the cloned folder
3. Run `poetry install`


## Usage

```
Usage: photos-of-me.py [OPTIONS] USERNAME PASSWORD TFA_CODE DIRECTORY

  Download "photos of me" to DIRECTORY, using Facebook credentials USERNAME
  and PASSWORD, and temporary TFA_CODE

  Instead of supplying PASSWORD on the command line, you can set the
  FB_PASSWORD environment variable:

      read -s FB_PASSWORD

      (Type your password, and then press <ENTER>.)

  USAGE

      photos-of-me.py [OPTIONS] USERNAME PASSWORD TFA_CODE DIRECTORY

Options:
  --workers INTEGER               Number of concurrent worker threads (default
                                  is 1).

  --wait / --no-wait              Wait a brief random amount of time between
                                  requests (default is wait).

  --offset INTEGER                Initial photo offset (default is 0).
  --log-level [DEBUG|INFO|WARNING|ERROR|CRITICAL]
                                  Set the logging level (default is INFO).
  --detach / --no-detach          Detach the Chrome browser (default is no
                                  detach).

  --help                          Show this message and exit.
```

### Quick start
```shell
poetry shell
source ./setup.sh
mkdir -p photos
python photos-of-me.py email@example.com $FB_PASSWORD 123567 photos
```
