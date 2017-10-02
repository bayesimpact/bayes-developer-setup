"""Integration to send Slack messages when new code reviews are sent in Reviewable."""
import enum
import json
import itertools
import os
import re
import traceback

import flask
import requests

# TODO(florian): Put GITHUB_TO_SLACK_LOGIN and error_slack_channel into an env variable.
_GITHUB_TO_SLACK_LOGIN = {
    'bmat06': 'benoit',
    'florianjourda': 'florian',
    'margaux2': 'margaux',
    'mlendale': 'marielaure',
    'john-mts': 'john',
    'pcorpet': 'pascal',
    'pnbt': 'guillaume',
    'pyduan': 'paul',
}
_ERROR_SLACK_CHANNEL = '@florian'
# The following variable is used for development, to check what messages are sent to all users.
_REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL = os.getenv('REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL')

app = flask.Flask(__name__)  # pylint: disable=invalid-name


@app.route('/', methods=['GET', 'POST'])
def index():
    """Health check endpoint."""
    return '''Integration to send Reviewable updates to Slack.
        Status: ✅
        Link Github webhook to post json to /handle_github_notification'''


@app.route('/handle_github_notification', methods=['POST'])
def handle_github_notification():
    """Receives a Github webhook notification and handles it to potentially ping devs on Slack."""
    github_event_type = flask.request.headers.get('X-GitHub-Event')
    github_notification = json.loads(flask.request.data)
    try:
        slack_messages = generate_slack_messages(github_event_type, github_notification)
        status_code = 200
    except NotEnoughDataException as err:
        # We could not figure out what issue to send updates about, so we do a noop.
        slack_messages = {}
        status_code = 200
    except Exception as err:  # pylint: disable=broad-except
        slack_messages = {
            _ERROR_SLACK_CHANNEL:
                'Error: {}\n\n{}\n'.format(err, traceback.format_exc())
        }
        status_code = 500
    # TODO(florian): Call Slack directly.
    zapier_to_slack_endpoint = 'https://hooks.zapier.com/hooks/catch/1946029/iy46wx/'
    zapier_slack_payloads = []
    if _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL:
        # To debug the integration, send only one message with all the info to the channel used
        # to test.
        all_messages_in_one = 'Messages from Reviewable:\n' + ('\n\n'.join([
            'To {}:\n{}'.format(slack_channel, slack_message)
            for slack_channel, slack_message in slack_messages.items()
        ]) if slack_messages else 'None')
        zapier_slack_payloads = [{
            'slack_channel': _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL,
            'slack_message': all_messages_in_one,
        }]
    else:
        zapier_slack_payloads = [
            {'slack_channel': slack_channel, 'slack_message': slack_message}
            for slack_channel, slack_message in slack_messages.items()
        ]

    for zapier_slack_payload in zapier_slack_payloads:
        response = requests.post(zapier_to_slack_endpoint, json=zapier_slack_payload)
        if response.status_code != 200:
            flask.abort(500, message='Error with Slack:\n{} {}'.format(
                response.status_code, response.text))
    return json.dumps(zapier_slack_payloads), status_code


class ReviewableEvent(enum.Enum):
    """Enum for the different type of events that happened on Reviewable."""
    ASSIGNED = 'ASSIGNED'
    COMMENTED = 'COMMENTED'
    RESPONDED = 'RESPONDED'
    APPROVED = 'APPROVED'


class CallToAction(enum.Enum):
    """Enum for the different type of action should be recommended to users on Slack."""
    REVIEW = 'REVIEW'
    SUBMIT = 'SUBMIT'
    CHECK_FEEDBACK = 'CHECK_FEEDBACK'
    CHECK_CHANGE = 'CHECK_CHANGE'
    ADDRESS_COMMENTS = 'ADDRESS_COMMENTS'
    WAIT_FOR_OTHER_REVIEWERS = 'WAIT_FOR_OTHER_REVIEWERS'


class SetupException(Exception):
    """Exception to warn about uncomplete setup."""
    pass


class NotEnoughDataException(Exception):
    """Exception when the github notification data does not tell us what issue it is about."""
    pass


class ExecutionException(Exception):
    """Exception to warn about communication issue with Github, Zappier or Slack."""
    pass


_GITHUB_PERSONAL_ACCESS_TOKEN = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN', '')
# TODO(pascal for florian): Please document all the regexp here, I'm a bit worried that this stops
# working if any other tool (reviewable or our own CI) change its syntax. Also document what kind
# of text they are capture if it's not obvious (like the github link regex)
_REVIEWABLE_COMMENT_REGEX = re.compile(
    r'^(?P<main_comment>(.|\n)*)\n\n(---)?\n\nReview status: (?P<review_status>.*)\n\n'
    r'---\n\n(?P<inline_comments>(.|\n)*)$',
    re.MULTILINE)
_REVIEWABLE_INLINE_COMMENT_LINK_REGEX = re.compile(r'https://reviewable\.io[^)]+', re.MULTILINE)
_REVIEWABLE_ASSIGN_REGEX = re.compile(r'\+@([\w]+)\b', re.MULTILINE)
_REVIEWABLE_HTML_EMOJI_REGEX = re.compile(r'<img class="emoji" title="([^"]+)"[^>]*>')
# From:    https://reviewable.io/reviews/bayesimpact/bob-emploi/5750
# Extract: repo: bayesimpact/bob-emploi
#          issue_number: 5750
_REVIEWABLE_URL_ISSUE_REGEX = re.compile(
    r'https://reviewable.io/reviews/(?P<repo>[^/]+/[^/]+)/(?P<issue_number>\d+)')
_GITHUB_REPO_NAME_REGEX = re.compile(r'^https://api.github.com/repos/(.*)$')

_EVENT_SLACK_TEMPLATES = {
    ReviewableEvent.ASSIGNED: '{who} needs your help to review {whose_change}',
    ReviewableEvent.COMMENTED: '{who} has commented on {whose_change}',
    ReviewableEvent.RESPONDED: '{who} has responsed to comments on {whose_change}',
    ReviewableEvent.APPROVED: '{who} has approved {whose_change}',
}

_CALL_TO_ACTION_TEMPLATES = {
    CallToAction.REVIEW: "Let's <{url}|check this code>!",
    CallToAction.SUBMIT: "Let's `git submit`!",
    CallToAction.CHECK_FEEDBACK: "Let's <{url}|check their feedback>!",
    CallToAction.CHECK_CHANGE: "Let's <{url}|check what they have changed>!",
    CallToAction.ADDRESS_COMMENTS: "Let's <{url}|address the remaining comments>",
    CallToAction.WAIT_FOR_OTHER_REVIEWERS: 'You now need to wait for the other reviewers.',
}


def generate_slack_messages(github_event_type, github_notification):
    """Generate all the messages to send on Slack to respond to a Github notification."""
    if github_event_type == 'issue_comment':
        github_resources = _get_all_resources_for_issue_comment_event(github_notification)
    elif github_event_type == 'status':
        # Ignore 'pending' status as we want to send notification for finishing, not for
        # starting ci pipeline.
        # if github_notification['state'] == 'pending':
            # return {}
        github_resources = _get_all_resources_for_status_event(github_notification)
    else:
        # We deal only with new comments and new ci/code review status notifications.
        return {}
    return _generate_slack_messages_for_new_status_or_comment(*github_resources)


def _get_all_resources_for_issue_comment_event(github_notification):
    """Fetch on Github API resources that are missing in the 'issue_comment' notification."""
    issue = github_notification['issue']

    statuses = _get_statuses_for_issue(issue)
    new_status = None
    comments = _get_github_api_ressource(issue['comments_url'])
    new_comment = github_notification['comment']
    return issue, statuses, new_status, comments, new_comment


def _get_all_resources_for_status_event(github_notification):
    """Fetch on Github API resources that are missing in the 'status' notification."""
    # Unfortunately 'status' event don't contain 'issue' data, so we need to fetch it.
    new_status = github_notification
    if new_status['context'].startswith('code-review/reviewable'):
        repo_and_issue_number =\
            _REVIEWABLE_URL_ISSUE_REGEX.match(github_notification['target_url']).groupdict()
        issue_url = 'https://api.github.com/repos/{repo}/issues/{issue_number}'.format(
            **repo_and_issue_number)
        issue = _get_github_api_ressource(issue_url)
        statuses = _get_statuses_for_issue(issue)
    elif new_status['context'].startswith('ci/circleci'):
        # It's really annoying, status events from CircleCI don't have any reference to the issue
        # number. We can try our chance by looking at 'statuses' which are accessible with the
        # commit sha, which we have. We can then look in the statuses if there are any status events
        # from Reviewable which have a referece to the issue number.
        sha = new_status['sha']

        statuses_url = new_status['repository']['statuses_url'].format(sha=sha)
        statuses = _get_github_api_ressource(statuses_url)
        reviewable_status = next((
            status for status in statuses
            if status['context'].startswith('code-review/reviewable')), None)
        if not reviewable_status:
            raise NotEnoughDataException(
                'Could not find any Reviewable status, '
                'we have no way to figure out the issue number')
        repo_and_issue_number =\
            _REVIEWABLE_URL_ISSUE_REGEX.match(reviewable_status['target_url']).groupdict()
        issue_url = 'https://api.github.com/repos/{repo}/issues/{issue_number}'.format(
            **repo_and_issue_number)
        issue = _get_github_api_ressource(issue_url)
    else:
        raise ExecutionException(
            "Does not support '{}' status context".format(new_status['context']))

    comments = _get_github_api_ressource(issue['comments_url'])
    new_comment = None
    return issue, statuses, new_status, comments, new_comment


def _get_statuses_for_issue(issue):
    pull_request_url = issue['pull_request']['url']
    pull_request = _get_github_api_ressource(pull_request_url)
    statuses_url = pull_request['_links']['statuses']['href']
    statuses = _get_github_api_ressource(statuses_url)
    return statuses


def _generate_slack_messages_for_new_status_or_comment(
        issue,
        statuses,
        new_status,
        comments,
        new_comment):
    """Prepare all data we need to decide what messages to generate."""
    # Note: new_comment is included in comments, and new_status in statuses.
    issue_owner = issue['user']['login']

    assignees = {assignee['login'] for assignee in issue['assignees']}
    # Remove the owner from the assignees if for some reason they self-assigned. This will simplify
    # our already complex logic later.
    assignees.discard(issue_owner)

    new_assignees =\
        {new_status['creator']['login']} if new_status\
        and new_status['context'].startswith('code-review') and new_status['state'] == 'pending'\
        else {}

    commentors = {comment['user']['login'] for comment in comments}
    new_commentor = new_comment['user']['login'] if new_comment else None

    is_ci_complete, lgtm_givers = _get_issue_ci_and_code_review_status(statuses)
    new_is_ci_complete, new_lgtm_givers = _get_issue_ci_and_code_review_status(
        [new_status] if new_status else [])
    # Make sure we don't count lgtm from user that were not assignees.
    has_assignees_without_lgtm = bool(assignees - lgtm_givers)

    last_comment = comments[-1] if comments else None
    unaddressed_comment_count = _get_unaddressed_comment_count(last_comment) if last_comment else 0
    has_unaddressed_comments = bool(unaddressed_comment_count)
    can_submit = not has_assignees_without_lgtm and not has_unaddressed_comments

    slack_messages = {}

    def add_slack_message(to_user, event, call_to_action, from_user_if_not_new_commentor=None):
        """Helper function to reduce boiler plate when calling _generate_slack_message."""
        from_user = from_user_if_not_new_commentor or new_commentor
        slack_messages.update(_generate_slack_message(
            from_user=from_user,
            event=event,
            to_user=to_user,
            call_to_action=call_to_action,
            issue=issue))

    # Here is all the logic tree about what message to send to whom.
    if not is_ci_complete:
        # Don't ping anyone if ci is not done!
        return {}

    if new_is_ci_complete:
        # The ci is now ready so we should ask the assignees to review it.
        for assignee in assignees:
            add_slack_message(assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW, issue_owner)
        return slack_messages

    if new_assignees:
        # We have new assignees to ask to review the change.
        for assignee in new_assignees:
            add_slack_message(assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW, issue_owner)
        return slack_messages

    # New comment is just a new comment.
    if new_commentor != issue_owner:
        # A reviewer gave some feedback to the issue owner.
        if new_lgtm_givers:
            # The reviewer gave a lgtm.
            if can_submit:
                add_slack_message(issue_owner, ReviewableEvent.APPROVED, CallToAction.SUBMIT)
            elif has_unaddressed_comments:
                # But there are still comments to address.
                add_slack_message(issue_owner, ReviewableEvent.APPROVED,
                                  CallToAction.ADDRESS_COMMENTS)
            else:
                # But there are still other reviewers to wait for.
                add_slack_message(issue_owner, ReviewableEvent.APPROVED,
                                  CallToAction.WAIT_FOR_OTHER_REVIEWERS)
        else:
            # The reviewer gave some comments.
            add_slack_message(issue_owner, ReviewableEvent.COMMENTED, CallToAction.CHECK_FEEDBACK)
        return slack_messages

    # The issue owner wrote some feedback.
    for assignee in assignees:
        if assignee in commentors:
            # If the assignee had written some comment before, it is likely the issue
            # owner just responded to them.
            add_slack_message(assignee, ReviewableEvent.RESPONDED,
                              CallToAction.CHECK_FEEDBACK)
        else:
            # The assignee had not contributed to the review yet, so it's time to do it.
            add_slack_message(assignee, ReviewableEvent.COMMENTED, CallToAction.REVIEW)
    if has_unaddressed_comments:
            # But there are still some comments they should address.
        add_slack_message(issue_owner, ReviewableEvent.COMMENTED,
                          CallToAction.ADDRESS_COMMENTS)

    return slack_messages


def _get_issue_ci_and_code_review_status(all_statuses):
    """Return the continous integration and code review status of the issue.

    Return None when the statuses did not give any info about the respective status.
    """
    # Check the format of statuses here: https://developer.github.com/v3/repos/statuses/
    all_statuses = sorted(all_statuses, key=lambda status: status['context'])
    statuses_by_context = itertools.groupby(all_statuses, key=lambda status: status['context'])
    is_ci_complete = False
    lgtm_givers = set()
    for context, context_statuses in statuses_by_context:
        if context.startswith('ci/'):
            last_status = max(context_statuses, key=lambda status: status['updated_at'])
            # TODO(florian): improve to work with multiple ci.
            is_ci_complete = last_status['state'] == 'success'
        elif context.startswith('code-review/'):
            code_review_statuses = sorted(
                context_statuses, key=lambda status: status['creator']['login'])
            statuses_by_user = itertools.groupby(
                code_review_statuses, key=lambda status: status['creator']['login'])
            for user_login, user_statuses in statuses_by_user:
                last_status = max(user_statuses, key=lambda status: status['updated_at'])
                if last_status['state'] == 'success':
                    lgtm_givers.add(user_login)
    return is_ci_complete, lgtm_givers


def _generate_slack_message(from_user, event, to_user, call_to_action, issue):
    slack_channel = '@' + _get_slack_login(to_user)
    # Extract 'bayesimpact/bob-emploi' from 'https://api.github.com/repos/bayesimpact/bob-emploi'.
    repository_name = _GITHUB_REPO_NAME_REGEX.match(issue['repository_url']).group(1)
    reviewable_url = 'https://reviewable.io/reviews/{}/{}'.format(repository_name, issue['number'])
    event_slack_string = _generate_event_slack_string(
        from_user, event, to_user, issue, reviewable_url)
    call_to_action_string = _generate_call_to_action_slack_string(call_to_action, reviewable_url)
    slack_message = '_{}:_\n{}'.format(event_slack_string, call_to_action_string)
    return {slack_channel: slack_message}


def _get_slack_login(github_login):
    """Return the slack login of a github user."""
    slack_login = _GITHUB_TO_SLACK_LOGIN.get(github_login)
    if slack_login is None:
        raise SetupException("Need to add Github user '{}' to GITHUB_TO_SLACK_LOGIN".format(
            github_login))
    return slack_login


def _generate_event_slack_string(from_user, event, to_user, issue, reviewable_url):
    if from_user == to_user:
        who = 'You'
    else:
        who = '@' + _get_slack_login(from_user)

    issue_owner = issue['user']['login']
    if issue_owner == to_user:
        whose = 'your'
    elif issue_owner == from_user:
        whose = 'their'
    else:
        whose = '@' + _get_slack_login(issue_owner) + "'s"
    whose_change = '{} change <{}|{}>'.format(whose, reviewable_url, issue['title'])

    event_slack_string = _EVENT_SLACK_TEMPLATES[event].format(who=who, whose_change=whose_change)
    return event_slack_string


def _generate_call_to_action_slack_string(call_to_action, first_comment_url):
    call_to_action_slack_string = _CALL_TO_ACTION_TEMPLATES[call_to_action].format(
        url=first_comment_url)
    return call_to_action_slack_string


def _get_comment_parts(comment_body):
    match = _REVIEWABLE_COMMENT_REGEX.match(comment_body)
    if not match:
        return {'main_comment': _replace_emoji_image_by_emoji_name(comment_body)}
    match_dict = match.groupdict()
    inline_comments_block = match_dict['inline_comments']
    inline_comment_links = _REVIEWABLE_INLINE_COMMENT_LINK_REGEX.findall(inline_comments_block)
    inline_comment_links = inline_comment_links[:-1]
    comment_info = match.groupdict()
    comment_info.update({
        'main_comment': _replace_emoji_image_by_emoji_name(match_dict['main_comment']),
        'inline_comment_links': inline_comment_links,
    })
    return comment_info


def _replace_emoji_image_by_emoji_name(html_text):
    return _REVIEWABLE_HTML_EMOJI_REGEX.sub(r'\1', html_text)


def _get_github_api_ressource(ressource_url):
    """Calls Github API to retrieve resource state."""
    if not _GITHUB_PERSONAL_ACCESS_TOKEN:
        raise SetupException('Need to define _GITHUB_PERSONAL_ACCESS_TOKEN env variable.')
    auth = tuple(_GITHUB_PERSONAL_ACCESS_TOKEN.split(':'))
    response = requests.get(ressource_url, auth=auth)
    if response.status_code != 200:
        raise ExecutionException('Could not retrieve object from Github API:\n{}\n{}: {}'.format(
            ressource_url, response.status_code, response.text
        ))
    return response.json()


def _get_unaddressed_comment_count(unused_comment):
    """Tells how many comments are still to be adressed by the review owner."""
    # TODO(florian): Get this value from comment.
    return 0


# We only need this for local development.
if __name__ == '__main__':
    app.run(debug=True)
