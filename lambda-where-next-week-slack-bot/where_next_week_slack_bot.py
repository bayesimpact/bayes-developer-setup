"""Integration to send Slack messages when new code reviews are sent in Reviewable."""
import collections
import datetime
import enum
import json
import itertools
import os
import re
import traceback

import flask
import requests
from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from apiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

_MONDAY = 0
_SATURDAY = 5
_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

_GOOGLE_CALENDAR_API_CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_name(
    'client_secret.json', scopes=['https://www.googleapis.com/auth/calendar.readonly'])

# Channel to send unexpected error messages to (typically channel of the admin like '@florian').
_ERROR_SLACK_CHANNEL = os.getenv('ERROR_SLACK_CHANNEL')
# Set of Slack users like ['florian'] who do not want to be notified on Slack.
_DISABLED_SLACK_LOGINS = set(json.loads(os.getenv('DISABLED_SLACK_LOGINS', '[]')))
# The following variable is used for development, to check what messages are sent to all users.
_REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL = os.getenv('REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL')
# Token to post messages on Slack. Can be retrieved in https://api.slack.com/apps/A74SCPGAK/oauth.
_SLACK_APP_BOT_TOKEN = os.getenv('SLACK_APP_BOT_TOKEN')
_SLACK_POST_MESSAGE_ENDPOINT = 'https://slack.com/api/chat.postMessage'

app = flask.Flask(__name__)  # pylint: disable=invalid-name


@app.route('/', methods=['GET', 'POST'])
def index():
    """Health check endpoint."""
    error_message = _get_missing_env_vars_error_message()
    if error_message:
        return error_message, 500

    return '''Where Next Week Slack bot.
        Status: ✅
        Link Github webhook to post json to /handle_github_notification'''


@app.route('/handle_github_notification', methods=['POST'])
def handle_github_notification():
    """Receives a Github webhook notification and handles it to potentially ping devs on Slack."""
    error_message = _get_missing_env_vars_error_message()
    if error_message:
        return error_message, 500

    github_event_type = flask.request.headers.get('X-GitHub-Event')
    github_notification = json.loads(flask.request.data)
    try:
        slack_messages = generate_slack_messages(github_event_type, github_notification)
        status_code = 200
    except NotEnoughDataException as err:
        # We could not figure out what pull request to send updates about, so we do a noop.
        slack_messages = {}
        status_code = 200
    except Exception as err:  # pylint: disable=broad-except
        slack_messages = {
            _ERROR_SLACK_CHANNEL:
                'Error: {}\n\n{}\n'.format(err, traceback.format_exc())
        }
        status_code = 500

    if slack_messages and _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL:
        # To debug the integration, send only one message with all the info to the channel used
        # to test.
        all_messages_in_one = 'Messages from Reviewable:\n' + ('\n\n'.join([
            'To {}:\n{}'.format(slack_channel, slack_message)
            for slack_channel, slack_message in slack_messages.items()
        ]) if slack_messages else 'None')
        slack_messages = {_REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL: all_messages_in_one}

    # Ping on Slack.
    for slack_channel, slack_message in slack_messages.items():
        response = requests.post(_SLACK_POST_MESSAGE_ENDPOINT, data={
            'token': _SLACK_APP_BOT_TOKEN,
            'channel': slack_channel,
            'text': slack_message,
            'as_user': True,
        })
        if response.status_code != 200:
            return 'Error with Slack:\n{} {}'.format(response.status_code, response.text), 500
    return json.dumps(slack_messages), status_code


def _get_missing_env_vars_error_message():
    error_message = ''
    if not _GITHUB_TO_SLACK_LOGIN:
        error_message += 'Need to set up GITHUB_TO_SLACK_LOGIN as env var in the format:' +\
            '{"florianjourda": "florian"}\n'
    if not _ERROR_SLACK_CHANNEL:
        error_message += 'Need to set up ERROR_SLACK_CHANNEL as env var in the format: #general'
    if not _SLACK_APP_BOT_TOKEN:
        error_message += 'Need to set up _SLACK_APP_BOT_TOKEN as env var in the format. Get it ' +\
            'from https://api.slack.com/apps/A74SCPGAK/oauth'
    return error_message


GithubEventParams = collections.namedtuple('GithubEventParams', [
    'pull_request', 'ci_status_events', 'new_ci_status_event', 'comments', 'new_comment'])


class SetupException(Exception):
    """Exception to warn about uncomplete setup."""
    pass


class NotEnoughDataException(Exception):
    """Exception when the github notification data does not tell us what pull request it's about."""
    pass


class ExecutionException(Exception):
    """Exception to warn about communication issue with Github, Zappier or Slack."""
    pass


def main():
    default_city = 'Lyon'
    users = [
        {'email': 'florian@bayesimpact.org', 'default_location': 'Lyon'},
        {'email': 'paul@bayesimpact.org', 'default_location': 'Paris'},
        {'email': 'john@bayesimpact.org', 'default_location': 'Lyon'},
        {'email': 'pascal@bayesimpact.org', 'default_location': 'Lyon'},
    ]
    start_time, end_time = _get_next_week_datetime_boundaries()
    all_locations_by_day = {}
    for user in users:
        location_by_day = _get_location_by_day_for_user(
            user['email'], user['default_location'], start_time, end_time)
        all_locations_by_day[user['email']] = location_by_day
    import pprint
    pprint.pprint(all_locations_by_day)


def _get_next_week_datetime_boundaries():
    now = datetime.datetime.now()
    # Next Monday at 00:00
    next_monday_morning = _get_next_weekday_datetime(now, _MONDAY)
    # For next Friday at 23:59 we simply get next Saturday at 00:00
    next_friday_night = _get_next_weekday_datetime(next_monday_morning, _SATURDAY)
    return next_monday_morning, next_friday_night


def _get_location_by_day_for_user(email, default_location, start_time, end_time):
    events_with_parsed_location = _get_events_with_parsed_location(email, start_time, end_time)
    location_by_day = _get_location_by_day_from_events(
        start_time, end_time, events_with_parsed_location)
    location_by_day = [
        locations if locations else default_location
        for locations in location_by_day
    ]
    return location_by_day


def _get_next_weekday_datetime(reference_day, weekday):
    days_ahead = weekday - reference_day.weekday()
    # If target day already happened this week
    if days_ahead <= 0:
        days_ahead += 7
    next_weekday_datetime = reference_day + datetime.timedelta(days_ahead)
    next_weekday_datetime_at_00_00 = next_weekday_datetime.replace(
        hour=0, minute=0, second=0, microsecond=0)
    return next_weekday_datetime_at_00_00


def _get_events_with_parsed_location(email, start_time, end_time):
    delegated_credentials = _GOOGLE_CALENDAR_API_CREDENTIALS.create_delegated(email)
    service = discovery.build('calendar', 'v3', credentials=delegated_credentials)
    start_time = start_time.isoformat() + 'Z'
    end_time = end_time.isoformat() + 'Z'
    eventsResult = service.events().list(
        calendarId=email,
        timeMin=start_time,
        timeMax=end_time,
        maxResults=500,
        singleEvents=True,
        fields='items(end,location,start,status,summary)',
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])
    confirmed_events = [event for event in events if event.get('status') == 'confirmed']
    print('{} events and {} confirmed'.format(len(events), len(confirmed_events)))
    events = [_update_event_with_parsed_location(event) for event in events]
    events = [event for event in events if event.get('parsed_location')]
    return events

_LOCACTIONS_REGEX = re.compile(r'(Paris|Lyon|OOO)', re.IGNORECASE)


def _update_event_with_parsed_location(event):
    match = _LOCACTIONS_REGEX.search(event.get('location', ''))
    if match:
        event['parsed_location'] = match[1].lower()
        return event

    match = _LOCACTIONS_REGEX.search(event.get('summary', ''))
    if match:
        event['parsed_location'] = match[1].lower()

    return event


def _get_location_by_day_from_events(start_time, end_time, events_with_parsed_location):
    # return events_with_parsed_location
    location_by_day = [set(), set(), set(), set(), set()]
    for event in events_with_parsed_location:
        # 2017-11-10T05:00:00+01:00
        print(event['start'])
        event_start_time = datetime.datetime.strptime(
            event['start']['dateTime'][:-6], _DATETIME_FORMAT)
        event_start_time = max(event_start_time, start_time)
        event_end_time = datetime.datetime.strptime(
            event['end']['dateTime'][:-6], _DATETIME_FORMAT)
        event_end_time = min(event_end_time, end_time)
        # print('In {} from {} to {}'.format(
        # event['parsed_location'], event_start_time, event_end_time))
        for weekday in range(event_start_time.weekday(), event_end_time.weekday() + 1):
            location_by_day[weekday].add(event['parsed_location'])
    return location_by_day


# We only need this for local development.
if __name__ == '__main__':
    main()
    # app.run(debug=True)
