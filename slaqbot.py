import os
import time
import calendar
import re
import pprint
import json
import spacy
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))
# starterbot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

filtered_rtm_types = ['desktop_notification', 'user_typing', 'user_change', 'dnd_updated_user', 'channel_created',
                      'file_comment_added', 'file_shared', 'member_joined_channel', 'file_public', 'reaction_added',
                      'bot_added', 'apps_changed', 'apps_installed', 'file_change', 'commands_changed',
                      'subteam_updated', 'team_join', 'reaction_removed', 'bot_changed']
active_convs = {}
faq_entries = []
parsed_faq = {}
pp = pprint.PrettyPrinter(indent=4)

nlp = spacy.load('en_core_web_lg')
# nlp = spacy.load('en')

# constants
RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
HELP_COMMAND = "help"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"
QUESTION_REGEX = "(can|how|what)(.*\??)$"
DEBUG_MODE = True if os.environ.get('DEBUG') else False


def parse_slack_events(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and metadata.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        # Filter out certain event types from processing
        #   This might seem backwards, but until I have a more exhaustive list of events we care about,
        #   this won't let other types of messages slip through the cracks while in debug mode - gabriel@
        if not event["type"] in filtered_rtm_types:
            debug_print(event)
        else:
            return None, None

        # Keep conversations threaded, so use `thread_ts` over `ts`
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
        for keyword in parsed_faq.keys():
            if keyword in command.lower():
                response = parsed_faq[keyword]

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
        for question in entry["questions"]:
            if question not in parsed_entries:
                parsed_entries[question] = {"answer": entry["answer"], "doc": nlp(question)}
            else:
                print("Error: Found duplicate keyword '{}' in pre-configured FAQ entries.".format(question))
                exit(1)
    debug_print(parsed_entries)

    for entry in parsed_entries:
        for other_entries in parsed_entries:
            print(entry + " :: " + other_entries)
            print(parsed_entries[entry]["doc"].similarity(parsed_entries[other_entries]["doc"]))
        print "\n"

    return parsed_entries


def read_faq_from_disk():
    """
        Loads the FAQ from disk into memory
    """
    return json.load(open("./faq.json"))


def track_conversation(timestamp, user):
    """
        Track all active conversations to pay attention to, and the users involved
    """
    if timestamp not in active_convs:
        debug_print("Adding a new conversation.")
        active_convs[timestamp] = {"users": [user], "start": calendar.timegm(time.gmtime())}
    elif user not in active_convs[timestamp]["users"]:
        debug_print("Adding a new user to an active conversation.")
        active_convs[timestamp]["users"].append(user)

    debug_print("Updating the last_updated field for the conversation")
    active_convs[timestamp]["last_updated"] = calendar.timegm(time.gmtime())

    debug_print(active_convs)


def is_active_conv(timestamp):
    """
        Checks whether or not a message that was sent belongs to an active conversation that the bot is in
    """
    debug_print("Checking to see if {} is an active conversation.".format(timestamp))
    debug_print(active_convs)
    return timestamp in active_convs


def debug_print(debug_data):
    """
        PrettyPrint to stdout if in debug mode
    """
    if DEBUG_MODE:
        pp.pprint(debug_data)


def nlp_debug_print(doc):
    """
    """
    print(["NLP dump of command:", doc])
    print("\nTokens in NLP doc:\n")
    for token in doc:
        print(token.text, token.lemma_, token.pos_, token.tag_, token.dep_, token.shape_, token.is_alpha, token.is_stop)
    print("\nEntities in NLP doc:\n")
    for ent in doc.ents:
        print(ent.text, ent.start_char, ent.end_char, ent.label_)


if __name__ == "__main__":
    # Parse the FAQ and expand all of the entries
    if len(faq_entries) == 0:
        faq_entries = read_faq_from_disk()
    debug_print(faq_entries)
    if len(parsed_faq) == 0:
        parsed_faq = parse_faq_entries(faq_entries)

    if slack_client.rtm_connect(with_team_state=False):
        print("SlAQ Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        starterbot_id = slack_client.api_call("auth.test")["user_id"]

        while True:
            command, metadata = parse_slack_events(slack_client.rtm_read())
            if command:
                debug_print("Encountered event to process.")
                track_conversation(metadata["ts"], metadata["user"])
                doc = nlp(command)
                nlp_debug_print(doc)
                handle_command(command, metadata)
            time.sleep(RTM_READ_DELAY)
    else:
        print("Connection failed. Exception traceback printed above.")
