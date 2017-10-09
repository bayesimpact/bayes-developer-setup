"""Integration to send Slack messages when new code reviews are sent in Reviewable."""
import collections
import enum
import json
import itertools
import os
import re
import traceback

import flask
import requests

_GITHUB_TO_SLACK_LOGIN = json.loads(os.getenv('GITHUB_TO_SLACK_LOGIN', '{}'))
_ERROR_SLACK_CHANNEL = os.getenv('ERROR_SLACK_CHANNEL')
# The following variable is used for development, to check what messages are sent to all users.
_REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL = os.getenv('REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL')

app = flask.Flask(__name__)  # pylint: disable=invalid-name


@app.route('/', methods=['GET', 'POST'])
def index():
    """Health check endpoint."""
    error_message = _get_missing_env_vars_error_message()
    if error_message:
        return error_message, 500

    return '''Integration to send Reviewable updates to Slack.
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
    # TODO(florian): Call Slack directly.
    zapier_to_slack_endpoint = 'https://hooks.zapier.com/hooks/catch/1946029/iy46wx/'
    if not slack_messages:
        # Don't ping anybody about no-op, even if _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL is set
        # because this creates way too many notifications.
        zapier_slack_payloads = []
    elif _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL:
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
            return 'Error with Slack:\n{} {}'.format(response.status_code, response.text), 500
    return json.dumps(zapier_slack_payloads), status_code


def _get_missing_env_vars_error_message():
    error_message = ''
    if not _GITHUB_TO_SLACK_LOGIN:
        error_message += 'Need to set up GITHUB_TO_SLACK_LOGIN as env var in the format:' +\
            '{"florianjourda": "florian"}\n'
    if not _ERROR_SLACK_CHANNEL:
        error_message += 'Need to set up ERROR_SLACK_CHANNEL as env var in the format: #general'
    return error_message


GithubEventParams = collections.namedtuple('GithubEventParams', [
    'pull_request', 'statuses', 'new_status', 'comments', 'new_comment'])


class ReviewableEvent(enum.Enum):
    """Enum for the different type of events that happened on Reviewable."""
    ASSIGNED = 'ASSIGNED'
    COMMENTED = 'COMMENTED'
    RESPONDED = 'RESPONDED'
    APPROVED = 'APPROVED'
    CI_FAILED = 'CI_FAILED'


class CallToAction(enum.Enum):
    """Enum for the different type of action should be recommended to users on Slack."""
    REVIEW = 'REVIEW'
    SUBMIT = 'SUBMIT'
    CHECK_FEEDBACK = 'CHECK_FEEDBACK'
    CHECK_CHANGE = 'CHECK_CHANGE'
    CHECK_CI = 'CHECK_CI'
    ADDRESS_COMMENTS = 'ADDRESS_COMMENTS'
    WAIT_FOR_OTHER_REVIEWERS = 'WAIT_FOR_OTHER_REVIEWERS'


class SetupException(Exception):
    """Exception to warn about uncomplete setup."""
    pass


class NotEnoughDataException(Exception):
    """Exception when the github notification data does not tell us what pull request it's about."""
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
_REVIEWABLE_URL_REGEX = re.compile(
    r'https://reviewable.io/reviews/(?P<repo>[^/]+/[^/]+)/(?P<number>\d+)')

_EVENT_SLACK_TEMPLATES = {
    ReviewableEvent.ASSIGNED: '{who} needs your help to review {whose_change}',
    ReviewableEvent.COMMENTED: '{who} has commented on {whose_change}',
    ReviewableEvent.RESPONDED: '{who} has responsed to comments on {whose_change}',
    ReviewableEvent.APPROVED: '{who} has approved {whose_change}',
    ReviewableEvent.CI_FAILED: '❗️ Continuous integration tests failed for {whose_change}'
}

_CALL_TO_ACTION_TEMPLATES = {
    CallToAction.REVIEW: "Let's <{code_review_url}|check this code>!",
    CallToAction.SUBMIT: "Let's `git submit`!",
    CallToAction.CHECK_FEEDBACK: "Let's <{code_review_url}|check their feedback>!",
    CallToAction.CHECK_CHANGE: "Let's <{code_review_url}|check what they have changed>!",
    CallToAction.CHECK_CI: "Let's <{ci_url}|check what the problem is>.",
    CallToAction.ADDRESS_COMMENTS: "Let's <{code_review_url}|address the remaining comments>.",
    CallToAction.WAIT_FOR_OTHER_REVIEWERS: 'You now need to wait for the other reviewers.',
}


def generate_slack_messages(github_event_type, github_notification):
    """Generate all the messages to send on Slack to respond to a Github notification."""
    if github_event_type == 'issue_comment':
        github_event_params = _get_all_resources_for_issue_comment_event(github_notification)
    elif github_event_type == 'status':
        github_event_params = _get_all_resources_for_status_event(github_notification)
    else:
        # We deal only with new comments and new CI/code review status notifications.
        return {}
    return _generate_slack_messages_for_new_status_or_comment(**github_event_params._asdict())


def _get_all_resources_for_issue_comment_event(github_notification):
    """Fetch on Github API resources that are missing in the 'issue_comment' notification."""
    # TODO(florian): we use issue in our code but we actually want a pull request. GitHub just
    # happens to use them a bit one for the other, but here our code should be clearer.
    issue = github_notification['issue']
    pull_request_url = issue['pull_request']['url']
    pull_request = _get_github_api_ressource(pull_request_url)
    statuses = _get_github_api_ressource(pull_request['statuses_url'])
    new_status = None
    comments = _get_github_api_ressource(pull_request['comments_url'])
    # Get the version of new_comment from the API instead of from the github notification.
    new_comment = next(
        comment for comment in comments
        if comment['id'] == github_notification['comment']['id'])
    return GithubEventParams(
        pull_request=pull_request,
        statuses=statuses,
        new_status=new_status,
        comments=comments,
        new_comment=new_comment)


def _get_all_resources_for_status_event(github_notification):
    """Fetch on Github API resources that are missing in the 'status' notification."""
    # Unfortunately 'status' event don't contain 'issue' data, so we need to fetch it.
    new_status = github_notification
    if new_status['context'].startswith('code-review/reviewable'):
        repo_and_number =\
            _REVIEWABLE_URL_REGEX.match(github_notification['target_url']).groupdict()
        pull_request_url = 'https://api.github.com/repos/{repo}/pulls/{number}'.format(
            **repo_and_number)
        pull_request = _get_github_api_ressource(pull_request_url)
    elif new_status['context'].startswith('ci/circleci'):
        filter_for_branch = '?base=master&head={}:{}'.format(
            new_status['repository']['owner']['login'], new_status['branches'][0]['name'])
        pull_request_url = new_status['repository']['pulls_url'].replace(
            '{/number}', filter_for_branch)
        pull_requests = _get_github_api_ressource(pull_request_url)
        if len(pull_requests) != 1:
            raise ExecutionException('Did not find a single pull_request: {}'.format(pull_requests))
        pull_request = pull_requests[0]
    else:
        raise ExecutionException(
            "Does not support '{}' status context".format(new_status['context']))

    statuses = _get_github_api_ressource(pull_request['statuses_url'])
    # Get the version of new_status from the API instead of from the github notification.
    new_status = next(status for status in statuses if status['id'] == new_status['id'])
    comments = _get_github_api_ressource(pull_request['comments_url'])
    new_comment = None
    return GithubEventParams(
        pull_request=pull_request,
        statuses=statuses,
        new_status=new_status,
        comments=comments,
        new_comment=new_comment)


def _generate_slack_messages_for_new_status_or_comment(
        pull_request, statuses, new_status, comments, new_comment):
    """Prepare all data we need to decide what messages to generate."""
    # Note: new_comment is included in comments, and new_status in statuses.
    reviewee = pull_request['user']['login']

    assignees = {assignee['login'] for assignee in pull_request['assignees']}
    # Remove the owner from the assignees if for some reason they self-assigned. This will simplify
    # our already complex logic later.
    assignees.discard(reviewee)

    new_assignees = _REVIEWABLE_ASSIGN_REGEX.findall(new_comment['body']) if new_comment else {}

    commentors = {comment['user']['login'] for comment in comments}
    new_commentor = new_comment['user']['login'] if new_comment else None

    ci_status, ci_url, lgtm_givers = _get_ci_and_code_review_status(statuses)
    new_ci_status, unused_new_ci_url, new_lgtm_givers = _get_ci_and_code_review_status(
        [new_status] if new_status else [])
    # Make sure we don't count lgtm from user that were not assignees.
    has_assignees_without_lgtm = bool(assignees - lgtm_givers)

    last_comment = comments[-1] if comments else None
    unaddressed_comment_count = _get_unaddressed_comment_count(last_comment) if last_comment else 0
    has_unaddressed_comments = bool(unaddressed_comment_count)
    can_submit = not has_assignees_without_lgtm and not has_unaddressed_comments

    if new_commentor:
        from_user = new_commentor
    elif new_ci_status:
        from_user = reviewee
    else:
        from_user = new_status['creator']['login']
    slack_messages = {}

    def add_slack_message(to_user, event, call_to_action):
        """Helper function to reduce boiler plate when calling _generate_slack_message."""
        slack_messages.update(_generate_slack_message(
            from_user=from_user,
            event=event,
            to_user=to_user,
            call_to_action=call_to_action,
            pull_request=pull_request,
            ci_url=ci_url))

    # Here is all the logic tree about what message to send to whom.
    if not ci_status or ci_status == 'pending':
        # Don't ping anyone if CI is not done!
        return {}

    if new_ci_status == 'failure':
        # CI tests just failed, warn the reviewee.
        add_slack_message(reviewee, ReviewableEvent.CI_FAILED, CallToAction.CHECK_CI)
        return slack_messages

    if new_ci_status == 'success':
        # The CI is now ready so we should ask the assignees to review it.
        for assignee in assignees:
            add_slack_message(assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW)
        return slack_messages

    if new_assignees:
        # We have new assignees to ask to review the change.
        for assignee in new_assignees:
            add_slack_message(assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW)
        return slack_messages

    # New comment is just a new comment.
    if new_commentor != reviewee:
        # A reviewer gave some feedback to the pull_request owner.
        if new_lgtm_givers:
            # The reviewer gave a lgtm.
            if can_submit:
                add_slack_message(reviewee, ReviewableEvent.APPROVED, CallToAction.SUBMIT)
            elif has_unaddressed_comments:
                # But there are still comments to address.
                add_slack_message(reviewee, ReviewableEvent.APPROVED,
                                  CallToAction.ADDRESS_COMMENTS)
            else:
                # But there are still other reviewers to wait for.
                add_slack_message(reviewee, ReviewableEvent.APPROVED,
                                  CallToAction.WAIT_FOR_OTHER_REVIEWERS)
        elif new_comment:
            # The reviewer gave some comments.
            add_slack_message(reviewee, ReviewableEvent.COMMENTED, CallToAction.CHECK_FEEDBACK)
        return slack_messages

    # The pull request owner wrote some feedback.
    for assignee in assignees:
        if assignee in commentors:
            # If the assignee had written some comment before, it is likely the pull request
            # owner just responded to them.
            add_slack_message(assignee, ReviewableEvent.RESPONDED,
                              CallToAction.CHECK_FEEDBACK)
        else:
            # The assignee had not contributed to the review yet, so it's time to do it.
            add_slack_message(assignee, ReviewableEvent.COMMENTED, CallToAction.REVIEW)
    if has_unaddressed_comments:
            # But there are still some comments they should address.
        add_slack_message(reviewee, ReviewableEvent.COMMENTED,
                          CallToAction.ADDRESS_COMMENTS)

    return slack_messages


def _get_ci_and_code_review_status(all_statuses):
    """Return the continous integration and code review status of the pull request.

    Return None when the statuses did not give any info about the respective status.
    """
    # Check the format of statuses here: https://developer.github.com/v3/repos/statuses/
    # TODO(add more doc abou the different event formats)
    all_statuses = sorted(all_statuses, key=lambda status: status['context'])
    statuses_by_context = itertools.groupby(all_statuses, key=lambda status: status['context'])
    ci_status = None
    ci_url = None
    lgtm_givers = set()
    for context, context_statuses in statuses_by_context:
        if context.startswith('ci/'):
            last_status = max(context_statuses, key=lambda status: status['updated_at'])
            # TODO(florian): improve to work with multiple CI.
            ci_status = last_status['state']
            ci_url = last_status['target_url']
            continue

        if context.startswith('code-review/'):
            def _get_reviewer_login(status):
                return status['creator']['login']
            code_review_statuses = sorted(
                context_statuses, key=_get_reviewer_login)
            statuses_by_user = itertools.groupby(
                code_review_statuses, key=_get_reviewer_login)
            for user_login, user_statuses in statuses_by_user:
                last_status = max(user_statuses, key=lambda status: status['updated_at'])
                if last_status['state'] == 'success':
                    lgtm_givers.add(user_login)
    return ci_status, ci_url, lgtm_givers


def _generate_slack_message(from_user, event, to_user, call_to_action, pull_request, ci_url):
    slack_channel = '@' + _get_slack_login(to_user)
    repository_name = pull_request['head']['repo']['full_name']
    code_review_url = 'https://reviewable.io/reviews/{}/{}'.format(
        repository_name, pull_request['number'])
    event_slack_string = _generate_event_slack_string(
        from_user, event, to_user, pull_request, code_review_url)
    call_to_action_string = _generate_call_to_action_slack_string(
        call_to_action, code_review_url, ci_url)
    slack_message = '_{}:_\n{}'.format(event_slack_string, call_to_action_string)
    return {slack_channel: slack_message}


def _get_slack_login(github_login):
    """Return the slack login of a github user."""
    slack_login = _GITHUB_TO_SLACK_LOGIN.get(github_login)
    if slack_login is None:
        raise SetupException("Need to add Github user '{}' to GITHUB_TO_SLACK_LOGIN".format(
            github_login))
    return slack_login


def _generate_event_slack_string(from_user, event, to_user, pull_request, code_review_url):
    if from_user == to_user:
        who = 'You'
    else:
        who = '@' + _get_slack_login(from_user)

    reviewee = pull_request['user']['login']
    if reviewee == to_user:
        whose = 'your'
    elif reviewee == from_user:
        whose = 'their'
    else:
        whose = '@' + _get_slack_login(reviewee) + "'s"
    whose_change = '{} change <{}|{}>'.format(whose, code_review_url, pull_request['title'])

    event_slack_string = _EVENT_SLACK_TEMPLATES[event].format(who=who, whose_change=whose_change)
    return event_slack_string


def _generate_call_to_action_slack_string(call_to_action, code_review_url, ci_url):
    call_to_action_slack_string = _CALL_TO_ACTION_TEMPLATES[call_to_action].format(
        code_review_url=code_review_url, ci_url=ci_url)
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
