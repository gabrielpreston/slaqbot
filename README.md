# SlAQ Bot

Slack Bot for FAQ Support

## Setup Instructions

* Install virtualenv: `pip install virtualenv`
* Create VENV: `virtualenv .slaqbot`
* Activate VENV: `source .slaqbot/bin/activate`
* Install dependencies: `pip install -r requirements.txt`

Startup with:

SLACK_BOT_TOKEN=xoxb-[RETRIEVE FROM SLACK UI] python slaqbot.py

Optional:

DEBUG=true SLACK_BOT_TOKEN=xoxb-[RETRIEVE FROM SLACK UI] python slaqbot.py
