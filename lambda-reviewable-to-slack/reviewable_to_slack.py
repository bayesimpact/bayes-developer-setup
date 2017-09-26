"""Integration to send Slack messages when new code reviews are sent in Reviewable."""
# import json
from enum import Enum
import json
import pprint
import os
import re
import traceback

from flask import Flask
from flask import request
import requests

app = Flask(__name__)  # pylint: disable=invalid-name


@app.route('/')
def index():
    """Main."""
    return '''Integration to send Reviewable updates to Slack.
        Status: ✅
        Link Github webhook to post json to /handle_github_notification''', 200


@app.route('/handle_github_notification', methods=['GET', 'POST'])
def handle_github_notification():
    """Receives a Github webhook notification and handles it to potentially ping devs on Slack."""
    github_notification = json.loads(request.data)
    # TODO(florian): Put github_to_slack_login and error_slack_channel into an env variable.
    github_to_slack_login = {
        'bmat06': 'benoit',
        'florianjourda': 'florian',
        'margaux2': 'margaux',
        'mlendale': 'marielaure',
        'john-mts': 'john',
        'pcorpet': 'pascal',
        'pnbt': 'guillaume',
        'pyduan': 'paul',
    }
    error_slack_channel = '@florian'
    slack_messages = generate_slack_messages(
        github_notification,
        github_to_slack_login,
        error_slack_channel)
    # TODO(florian): Call Slack directly
    zapier_to_slack_endpoint = 'https://hooks.zapier.com/hooks/catch/1946029/iy46wx/'

    for slack_channel, slack_message in slack_messages.items():
        response = requests.post(zapier_to_slack_endpoint, json={
            'slack_channel': '@florian',
            'slack_message': 'To {}:\n{}'.format(slack_channel, slack_message)
        })
        if response.status_code != 200:
            return 'Error with Slack:\n{} {}'.format(response.status_code, response.text), 500
    return 'Messages for Slack:\n{}'.format(pprint.pformat(slack_messages)), 200


class ReviewableEvent(Enum):
    """Enum for the different type of events that happened on Reviewable."""
    ASSIGNED = 'ASSIGNED'
    COMMENTED = 'COMMENTED'
    RESPONDED = 'RESPONDED'
    APPROVED = 'APPROVED'


class CallToAction(Enum):
    """Enum for the different type of action should be recommended to users on Slack."""
    REVIEW = 'REVIEW'
    SUBMIT = 'SUBMIT'
    CHECK_FEEDBACK = 'CHECK_FEEDBACK'
    CHECK_CHANGE = 'CHECK_CHANGE'
    ADDRESS_COMMENTS = 'ADDRESS_COMMENTS'
    WAIT_FOR_OTHER_REVIEWERS = 'WAIT_FOR_OTHER_REVIEWERS'


_GITHUB_PERSONAL_ACCESS_TOKEN = os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN', '')

_REVIEWABLE_COMMENT_REGEX = r'^(?P<main_comment>(.|\n)*)\n\n(---)?\n\nReview status: (?P<review_status>.*)\n\n---\n\n(?P<inline_comments>(.|\n)*)$'  # nopep8 # pylint: disable=line-too-long
_REVIEWABLE_INLINE_COMMENT_LINK_REGEX = r'https://reviewable\.io[^)]+'
_REVIEWABLE_ASSIGN_REGEX = r'@([\w]+)\b'
_REVIEWABLE_DEMO_REGEX = r'.*(Demo ready for review|No demo to review)'
_REVIEWABLE_HTML_EMOJI_REGEX = r'<img class="emoji" title="([^"]+)"[^>]*>'
_REVIEWABLE_LGTM_REGEX = r'.*:lgtm(_strong)?:'
_REVIEWABLE_ALL_COMMENTS_ADDRESSED = \
    r'Review status: \d+ of \d+ files reviewed at latest revision, all discussions resolved.'
_GITHUB_LINK_REGEX = r'\[([^]]+)\]\(([^)]+)\)'
_SLACK_LINK_REGEX = r'<\2|\1>'


def generate_slack_messages(
        github_notification,
        github_to_slack_login,
        error_slack_channel='#general'):
    """Generate all the messages to send on Slack to respond to a Github notification."""
    action = github_notification.get('action')
    issue = github_notification.get('issue')
    new_comment = github_notification.get('comment')
    # We deal only with new comments.
    try:
        if action == 'created' and issue and new_comment:
            return _generate_slack_messages_for_new_comment(
                issue,
                new_comment,
                github_to_slack_login,
            )
        else:
            return {}
    except Exception as err:  # pylint: disable=broad-except
        return {
            error_slack_channel: 'Error: {}\n\n{}\nWhen processing Github notification:\n{}'.format(
                err,
                traceback.format_exc(),
                pprint.pformat(github_notification),
            )
        }


def _generate_slack_messages_for_new_comment(issue, new_comment, github_to_slack_login):
    # Get all data we need to decide what messages to generate.
    slack_messages = {}

    # Note: new_comment is included in comments.
    comments = _get_github_api_ressource(issue['comments_url'])
    issue_owner = issue['user']['login']

    assignees = {assignee['login'] for assignee in issue['assignees']}
    # Remove the owner from the assignees if for some reason they self-assigned. This will simplify
    # our already complex login later.
    assignees -= {issue_owner}
    new_comment_assignees = re.findall(
        _REVIEWABLE_ASSIGN_REGEX, new_comment['body'], re.MULTILINE)

    commentors = {comment['user']['login'] for comment in comments}
    new_commentor = new_comment['user']['login']

    lgtm_givers = _get_lgtm_givers(comments)
    new_comment_is_lgtm = bool(_get_lgtm_givers([new_comment]))

    is_demo_ready = _get_is_demo_ready(comments)
    new_comment_is_demo_ready = _get_is_demo_ready([new_comment])

    unaddressed_comment_count = _get_unaddressed_comment_count(new_comment)
    can_submit = (lgtm_givers == len(assignees)) and unaddressed_comment_count == 0

    def add_slack_message(to_user, event, call_to_action):
        """Helper function to reduce boiler plate when calling _generate_slack_message."""

        def get_slack_login(github_login):
            """Return the slack login of a github user."""
            slack_login = github_to_slack_login.get(github_login)
            if slack_login is None:
                raise Exception('Need to add Github user {} to github_to_slack_login'.format(
                    github_login))
            return slack_login

        slack_messages.update(_generate_slack_message(
            from_user=new_commentor,
            event=event,
            to_user=to_user,
            call_to_action=call_to_action,
            issue=issue,
            get_slack_login=get_slack_login))

    # Here is all the logic tree about what message to send to whom.
    if not is_demo_ready:
        # Don't ping anyone if the demo is not ready!
        return slack_messages

    if new_comment_is_demo_ready:
        # The demo is now ready so we should ask the assignees to review it.
        for assignee in assignees:
            add_slack_message(
                assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW)
    elif new_comment_assignees:
        # We have new assignees to ask to review the change.
        for assignee in new_comment_assignees:
            add_slack_message(
                assignee, ReviewableEvent.ASSIGNED, CallToAction.REVIEW)
    else:
        # New comment is just a new comment.
        if new_commentor != issue_owner:
            # A reviewer gave some feedback to the issue owner.
            if new_comment_is_lgtm:
                # The reviewer gave a lgtm.
                if can_submit:
                    add_slack_message(
                        issue_owner, ReviewableEvent.APPROVED, CallToAction.SUBMIT)
                elif unaddressed_comment_count != 0:
                    # But there are still comments to address.
                    add_slack_message(issue_owner, ReviewableEvent.APPROVED,
                                      CallToAction.ADDRESS_COMMENTS)
                else:
                    # But there are still other reviewers to wait for.
                    add_slack_message(issue_owner, ReviewableEvent.APPROVED,
                                      CallToAction.WAIT_FOR_OTHER_REVIEWERS)
            else:
                # The reviewer gave some comments.
                add_slack_message(
                    issue_owner, ReviewableEvent.COMMENTED, CallToAction.CHECK_FEEDBACK)
        else:
            # The issue owner wrote some feedback.
            for assignee in assignees:
                if assignee in commentors:
                    # If the assignee had written some comment before, it is likely the issue
                    # owner just responded to them.
                    add_slack_message(
                        assignee, ReviewableEvent.RESPONDED, CallToAction.CHECK_FEEDBACK)
                else:
                    # The assignee had not contributed to the review yet, so it's time to do it.
                    add_slack_message(
                        assignee, ReviewableEvent.COMMENTED, CallToAction.REVIEW)
            if unaddressed_comment_count:
                    # But there are still some comments they should address.
                add_slack_message(
                    issue_owner, ReviewableEvent.COMMENTED, CallToAction.ADDRESS_COMMENTS)

    return slack_messages


def _generate_slack_message(
        from_user,
        event,
        to_user,
        call_to_action,
        issue,
        get_slack_login):
    slack_channel = '@' + get_slack_login(to_user)

    reviewable_url = 'https://reviewable.io/reviews/bayesimpact/paul-emploi/{}'.format(
        issue['number'])
    event_slack_string = _generate_event_slack_string(
        from_user, event, to_user, issue, reviewable_url, get_slack_login)
    call_to_action_string = _generate_call_to_action_slack_string(call_to_action, reviewable_url)
    slack_message = '_{}:_\n{}'.format(event_slack_string, call_to_action_string)
    return {slack_channel: slack_message}


def _generate_event_slack_string(from_user, event, to_user, issue, reviewable_url, get_slack_login):
    event_slack_templates = {
        ReviewableEvent.ASSIGNED: '{who} needs your help to review {whose_change}',
        ReviewableEvent.COMMENTED: '{who} has commented on {whose_change}',
        ReviewableEvent.RESPONDED: '{who} has responsed to comments on {whose_change}',
        ReviewableEvent.APPROVED: '{who} has approved {whose_change}',
    }

    if from_user == to_user:
        who = 'You'
    else:
        who = '@' + get_slack_login(from_user)

    issue_owner = issue['user']['login']
    if issue_owner == to_user:
        whose = 'your'
    elif issue_owner == from_user:
        whose = 'their'
    else:
        whose = '@' + get_slack_login(issue_owner) + "'s"
    whose_change = '{} change <{}|{}>'.format(
        whose, reviewable_url, issue['title'])

    event_slack_string = event_slack_templates[event].format(
        who=who, whose_change=whose_change)
    return event_slack_string


def _generate_call_to_action_slack_string(call_to_action, first_comment_url):
    call_to_action_templates = {
        CallToAction.REVIEW: "Let's <{url}|check this code>!",
        CallToAction.SUBMIT: "Let's `git submit`!",
        CallToAction.CHECK_FEEDBACK: "Let's <{url}|check their feedback>!",
        CallToAction.CHECK_CHANGE: "Let's <{url}|check what they have changed>!",
        CallToAction.ADDRESS_COMMENTS: "Let's <{url}|address the remaining comments>",
        CallToAction.WAIT_FOR_OTHER_REVIEWERS: 'You now need to wait for the other reviewers.',
    }
    call_to_action_slack_string = call_to_action_templates[call_to_action].format(
        url=first_comment_url)
    return call_to_action_slack_string


def _get_comment_parts(comment_body):
    match = re.match(_REVIEWABLE_COMMENT_REGEX, comment_body, re.MULTILINE)
    if not match:
        return {
            'main_comment': comment_body
        }
    match_dict = match.groupdict()
    inline_comments_block = match_dict['inline_comments']
    inline_comment_links = re.findall(
        _REVIEWABLE_INLINE_COMMENT_LINK_REGEX, inline_comments_block, re.MULTILINE)
    inline_comment_links = inline_comment_links[:-1]
    comment_info = match.groupdict()
    comment_info.update({
        'main_comment': re.sub(_REVIEWABLE_HTML_EMOJI_REGEX, r'\1', match_dict['main_comment']),
        'inline_comment_links': inline_comment_links,
    })
    return comment_info


def _get_github_api_ressource(ressource_url):
    """Calls Github API to retrieve resource state."""
    auth = tuple(_GITHUB_PERSONAL_ACCESS_TOKEN.split(':'))
    print("{} => {}".format(_GITHUB_PERSONAL_ACCESS_TOKEN, auth))
    response = requests.get(ressource_url, auth=auth)
    if response.status_code != 200:
        raise Exception('Could not retrieve object from Github API:\n{}\n{}: {}'.format(
            ressource_url, response.status_code, response.text
        ))
    return response.json()


def _get_lgtm_givers(comments):
    """Returns Github user logins who gave a lgtm in the review comments."""
    return {
        comment['user']['login'] for comment in comments
        if re.match(_REVIEWABLE_LGTM_REGEX, comment['body'], re.MULTILINE)
    }


def _get_is_demo_ready(comments):
    """Tells whether one comment said the demo is ready or not needed."""
    return any(
        re.match(_REVIEWABLE_DEMO_REGEX, comment['body'], re.MULTILINE)
        for comment in comments
    )


def _get_unaddressed_comment_count(comment):  # pylint: disable=unused-argument
    """Tells how many comments are still to be adressed by the review owner."""
    # TODOA(florian): Get this value from comment
    return 0


# We only need this for local development.
if __name__ == '__main__':
    app.run()
