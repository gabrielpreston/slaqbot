import os
import time
import re
import pprint
import json
import logging
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
# starterbot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

pp = pprint.PrettyPrinter(indent=4)

# constants
RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
HELP_COMMAND = "help"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"
QUESTION_REGEX = "(can|how|what)(.*\??)$"
FILTERED_OUT_TYPES = ["desktop_notification", "user_typing"]
DEBUG_MODE = os.environ.get('DEBUG')
ACTIVE_CONVS = {}
FAQ_ENTRIES = []
PARSED_FAQ = {}


class MyEventHandler(PatternMatchingEventHandler):
    def on_moved(self, event):
        super(MyEventHandler, self).on_moved(event)
        logging.info("File {} was just moved".format(event.src_path))

    def on_created(self, event):
        super(MyEventHandler, self).on_created(event)
        logging.info("File {} was just created".format(event.src_path))

    def on_deleted(self, event):
        super(MyEventHandler, self).on_deleted(event)
        logging.info("File {} was just deleted".format(event.src_path))

    def on_modified(self, event):
        super(MyEventHandler, self).on_modified(event)
        logging.info("File {} was just modified".format(event.src_path))


def parse_slack_events(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and metadata.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        # Filter out certain event types from debug printing
        if not event["type"] in FILTERED_OUT_TYPES:
            debug_print(event)

        if "thread_ts" in event:
            ts = event["thread_ts"]
        elif "ts" in event:
            ts = event["ts"]
        else:
            ts = None

        # Look for qualifying events

        # Standard message to room
        # if event["type"] == "message" and "subtype" not in event:
        if event["type"] == "message" and "subtype" not in event:
            user_id, message = parse_direct_mention(event["text"])
            if user_id == starterbot_id or is_active_conv(ts):
                return message, \
                       {
                           "channel": event["channel"],
                           "user": event["user"],
                           "ts": ts
                       }

    return None, None


def parse_direct_mention(message_text):
    """
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention, returns None
    """
    matches = re.search(MENTION_REGEX, message_text)
    # the first group contains the username, the second group contains the remaining message
    return (matches.group(1), matches.group(2).strip()) if matches else (None, message_text.strip())


def handle_command(command, metadata):
    """
        Executes bot command if the command is known
    """
    # Default response is help text for the user
    default_response = "Not sure what you mean, <@{}>. Try *{}*.".format(metadata["user"], HELP_COMMAND)

    # Finds and executes the given command, filling in response
    response = None

    # Check command for FAQ keywords
    if is_question(command.lower()):
        debug_print("Found a question")
        for keyword in PARSED_FAQ.keys():
            if keyword in command.lower():
                response = PARSED_FAQ[keyword]

    # Sends the response back to the channel
    slack_client.api_call(
        "chat.postMessage",
        channel=metadata["channel"],
        text=response or default_response,
        thread_ts=metadata["ts"]
    )


def is_question(text):
    """
        Tries to determine whether or not a user's message was a question
    """
    debug_print("Checking whether or not a question may have been asked.")
    matches = re.search(QUESTION_REGEX, text)
    debug_print(matches)
    return True if matches else False


def parse_faq_entries(entries):
    """
        Iterate through the condensed FAQ entries to expand all of the keywords and answers
    """
    parsed_entries = {}
    for entry in entries:
        for keyword in entry["keywords"]:
            if keyword not in parsed_entries:
                parsed_entries[keyword] = entry["answer"]
            else:
                print("Error: Found duplicate keyword '{}' in pre-configured FAQ entries.".format(keyword))
                exit(1)

    return parsed_entries


def read_faq_from_disk():
    """
        Loads the FAQ from disk into memory
    """
    return json.load(open("./faq.json"))


def add_conversation(timestamp, user):
    """
        Track all active conversations to pay attention to, and the users involved
    """
    if timestamp not in ACTIVE_CONVS:
        debug_print("Adding a new conversation.")
        ACTIVE_CONVS[timestamp] = [user]
    elif user not in ACTIVE_CONVS[timestamp]:
        debug_print("Adding a new user to an active conversation.")
        ACTIVE_CONVS[timestamp].append(user)
    debug_print(ACTIVE_CONVS)


def is_active_conv(timestamp):
    """
        Checks whether or not a message that was sent belongs to an active conversation that the bot is in
    """
    debug_print("Checking to see if {} is an active conversation.".format(timestamp))
    debug_print(ACTIVE_CONVS)
    return timestamp in ACTIVE_CONVS


def debug_print(debug_data):
    """
        PrettyPrint to stdout if in debug mode
    """
    if DEBUG_MODE == "true":
        pp.pprint(debug_data)


if __name__ == "__main__":
    # Parse the FAQ and expand all of the entries
    if len(FAQ_ENTRIES) == 0:
        FAQ_ENTRIES = read_faq_from_disk()
    if len(PARSED_FAQ) == 0:
        PARSED_FAQ = parse_faq_entries(FAQ_ENTRIES)
    debug_print(PARSED_FAQ)

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = './faq.json'
    watched_dir = os.path.split(path)[0]
    event_handler = MyEventHandler(patterns=[path])
    observer = Observer()
    observer.schedule(event_handler, watched_dir, recursive=True)
    observer.start()

    if slack_client.rtm_connect(with_team_state=False):
        print("SlAQ Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        starterbot_id = slack_client.api_call("auth.test")["user_id"]

        try:
            while True:
                command, metadata = parse_slack_events(slack_client.rtm_read())
                if command:
                    debug_print("Encountered event to process.")
                    add_conversation(metadata["ts"], metadata["user"])
                    handle_command(command, metadata)
                time.sleep(RTM_READ_DELAY)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        print("Connection failed. Exception traceback printed above.")
