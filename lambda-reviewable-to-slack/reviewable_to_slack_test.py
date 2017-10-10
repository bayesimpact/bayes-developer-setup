"""Tests for the integration between Reviewable/Github webhooks and Slack."""
import json
import unittest

import mock

import reviewable_to_slack

_ERROR_SLACK_CHANNEL = '#general'
_GITHUB_TO_SLACK_LOGIN = {
    'guillaume_chaslot_reviewee': 'guillaume',
    'pascal_corpet_reviewer_1': 'pascal',
    'john_metois_reviewer_2': 'john',
}
_REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL = ''


@mock.patch('reviewable_to_slack._GITHUB_TO_SLACK_LOGIN', _GITHUB_TO_SLACK_LOGIN)
@mock.patch('reviewable_to_slack._ERROR_SLACK_CHANNEL', _ERROR_SLACK_CHANNEL)
@mock.patch(
    'reviewable_to_slack._REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL',
    _REDIRECT_ALL_SLACK_MESSAGES_TO_CHANNEL)
class ReviewableToSlackTestCase(unittest.TestCase):
    """Unit tests for the integration between Reviewable notification and Slack."""

    def setUp(self):
        reviewable_to_slack.app.testing = True
        self._app = reviewable_to_slack.app.test_client()

        self.maxDiff = None  # pylint: disable=invalid-name
        # State simulating what is present on Github. This will be updated by
        # _simulate_notification_for_new_comment to simulate scenarios, which will
        # change what requests.get on Github API returns.
        self._github_issue = {
            'number': 5670,
            'user': {'login': 'guillaume_chaslot_reviewee'},
            'pull_request': {
                'url': 'https://api.github.com/repos/bayesimpact/bob-emploi/pulls/5670',
            }
        }
        self._github_assignees = set()
        # Comments and statuses are not given directly inside the issue json in the Github API.
        self._github_issue_comments = []
        self._github_issue_statuses = []
        self._github_pull_request = {
            'number': 5670,
            'title': 'Fixed some bug',
            'user': {'login': 'guillaume_chaslot_reviewee'},
            'assignees': [],
            'comments_url':
                'https://api.github.com/repos/bayesimpact/bob-emploi/issues/5670/comments',
            'statuses_url': 'https://api.github.com/repos/bayesimpact/bob-emploi/statuses/353ff7e711d0dab6cff5e7e90026c7f8eff05016',  # nopep8 # pylint: disable=line-too-long
            'repository_url': 'https://api.github.com/repos/bayesimpact/bob-emploi',
            'head': {
                'repo': {
                    'full_name': 'bayesimpact/bob-emploi',
                    'owner': {'login': 'bayesimpact'}
                },
            },
        }
        self._github_statuses = []

        # Fake ID to increment to give to statuses.
        self._comment_id = 1000

        # Fake ID to increment to give to statuses.
        self._status_id = 2000

        # Fake time to create fake timestamps.
        self._fake_time_seconds = 0

        # Patch applied to all tests.
        requests_get_patcher = mock.patch('requests.get')
        mock_requests_get = requests_get_patcher.start()
        self.addCleanup(requests_get_patcher.stop)
        # We change requests.get to return the simulated state of the Github issue.
        self._make_requests_return_state(mock_requests_get)

        requests_post_patcher = mock.patch('requests.post')
        mock_requests_post = requests_post_patcher.start()
        self.addCleanup(requests_post_patcher.stop)
        self._make_requests_post_return_ok(mock_requests_post)

        super(ReviewableToSlackTestCase, self).setUp()

    def _make_requests_return_state(self, mock_requests_get):
        """Change request.get so that it returns the current state of the Github issue."""
        # TODO(florian): Check the 'auth'.
        def _requests_get_side_effect(url, **unused_kwargs):
            """Return the current state of the Github issue."""
            response = mock.MagicMock()
            url_to_response = {
                'https://api.github.com/repos/bayesimpact/bob-emploi/issues/5670':
                    self._github_issue,
                'https://api.github.com/repos/bayesimpact/bob-emploi/issues/5670/comments':
                    self._github_issue_comments,
                'https://api.github.com/repos/bayesimpact/bob-emploi/pulls/5670':
                    self._github_pull_request,
                'https://api.github.com/repos/bayesimpact/bob-emploi/pulls?base=master&head=bayesimpact:guillaume-fixed-some-bug':  # nopep8 # pylint: disable=line-too-long
                    [self._github_pull_request],
                'https://api.github.com/repos/bayesimpact/bob-emploi/statuses/353ff7e711d0dab6cff5e7e90026c7f8eff05016':  # nopep8 # pylint: disable=line-too-long
                    self._github_statuses,
            }
            # Will fail if url is not defined in mocked_calls.
            response.json.return_value = url_to_response[url]
            response.status_code = 200
            return response
        mock_requests_get.side_effect = _requests_get_side_effect

    def _make_requests_post_return_ok(self, mock_requests_post):
        """Change request.post so that it's a noop."""
        def _requests_post_side_effect(unused_url, **unused_kwargs):
            """Make requests.post be a noop."""
            # TODO(florian): test what was slack messages were sent to requests.post instead
            # of looking at the response of /handle_github_notification.
            response = mock.MagicMock()
            response.status_code = 200
            return response
        mock_requests_post.side_effect = _requests_post_side_effect

    def _simulate_notification_for_new_status(  # pylint: disable=invalid-name
            self,
            context,
            state,
            creator,
            target_url,
            sha=None):
        """Return a new status in Github and create Github notification."""
        status = {
            'id': self._status_id,
            'context': context,
            'creator': {'login': creator},
            'state': state,
            'target_url': target_url,
            'updated_at': self._get_fake_time(),
            'branches': [{
                'name': 'guillaume-fixed-some-bug',
            }],
            'repository': {
                'owner': {'login': 'bayesimpact'},
                'pulls_url': 'https://api.github.com/repos/bayesimpact/bob-emploi/pulls{/number}',
            },
        }
        self._status_id = self._status_id + 1
        if sha:
            status['sha'] = sha
        # Github orders statuses in reverse chronological order.
        self._github_statuses.insert(0, status)
        github_notification = status
        return github_notification

    def _get_fake_time(self):
        self._fake_time_seconds += 1
        return '2017-10-04T09:50:%02dZ' % (self._fake_time_seconds,)

    def _simulate_notification_for_new_comment(  # pylint: disable=invalid-name
            self,
            commentor,
            comment_body,
            new_assignees=None):
        """Return a new comment in the Github issue and create Github notification."""
        comment = {
            'id': self._comment_id,
            'user': {'login': commentor},
            'body': comment_body,
        }
        self._comment_id = self._comment_id + 1
        self._add_assignees(new_assignees)
        # The value of _github_issue_comments will be given back by the mocked API call
        # that gets Github comments.
        self._github_issue_comments.append(comment)
        github_notification = {
            'action': 'created',
            'comment': comment,
            'issue': self._github_issue,
        }
        return github_notification

    def _add_assignees(self, new_assignees):
        self._github_assignees.update(new_assignees or set())
        self._github_pull_request['assignees'] = [
            {'login': github_login}
            for github_login in self._github_assignees
        ]

    def _generate_slack_messages_for_new_ci_status(self, state):  # pylint: disable=invalid-name
        """Get the Slack messages that would be generate when a new CI statis is created."""
        github_notification = self._simulate_notification_for_new_status(
            context='ci/circleci: build-and-test',
            state=state,
            creator='guillaume_chaslot_reviewee',
            sha='353ff7e711d0dab6cff5e7e90026c7f8eff05016',
            target_url='https://circleci.com/gh/bayesimpact/bob-emploi/13420')
        slack_messages = self._handle_github_notification('status', github_notification)
        return slack_messages

    def _generate_slack_messages_for_new_lgtm(self, lgtm_giver):
        """Get the Slack messages that would be generate when a new CI statis is created."""
        github_notification = self._simulate_notification_for_new_status(
            context='code-review/reviewable',
            state='success',
            creator=lgtm_giver,
            target_url='https://reviewable.io/reviews/bayesimpact/bob-emploi/5670')
        slack_messages = self._handle_github_notification('status', github_notification)
        return slack_messages

    def _generate_slack_messages_for_new_comment(self, commentor, comment_body, new_assignees=None):
        """Get the Slack messages that would be generate when a new Github comment is created."""
        github_notification = self._simulate_notification_for_new_comment(
            commentor,
            comment_body,
            new_assignees)
        slack_messages = self._handle_github_notification('issue_comment', github_notification)
        return slack_messages

    def _handle_github_notification(self, github_event_type, github_notification):
        response = self._app.post(
            '/handle_github_notification',
            data=json.dumps(github_notification),
            content_type='application/json',
            headers={'X-GitHub-Event': github_event_type})
        slack_messages = json.loads(response.data)
        return slack_messages

    # As the name of the tests are self-explanatory, we don't need docstrings for them.
    # pylint: disable=missing-docstring
    def test_reviewee_is_warned_when_ci_fails(self):
        slack_messages = self._generate_slack_messages_for_new_ci_status('failure')
        self.assertEqual([{
            'slack_channel': '@guillaume',
            'slack_message':
                '_❗️ Continuous integration tests failed for your change ' +
                '<https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|Fixed some bug>:_\n' +
                "Let's <https://circleci.com/gh/bayesimpact/bob-emploi/13420|check what the " +
                'problem is>.'
        }], slack_messages)

    @mock.patch('reviewable_to_slack._DISABLED_SLACK_LOGINS', {'guillaume'})
    def test_disable_slack_login_does_not_get_message(self):
        slack_messages = self._generate_slack_messages_for_new_ci_status('failure')
        self.assertEqual([], slack_messages)

    def test_review_workflow_when_adding_assignee_before_demo_is_ready(self):
        slack_messages = self._generate_slack_messages_for_new_ci_status('pending')
        self.assertEqual([], slack_messages, 'No message expected before CI is done')
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@pascal_corpet_reviewer_1 \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['pascal_corpet_reviewer_1']
        )
        self.assertEqual([], slack_messages, 'No message expected before CI is done')
        slack_messages = self._generate_slack_messages_for_new_ci_status('success')
        self.assertEqual([{
            'slack_channel': '@pascal',
            'slack_message':
                '_@guillaume needs your help to review their change ' +
                '<https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|Fixed some bug>:_\n' +
                "Let's <https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|check this code>!"
        }], slack_messages)

    def test_review_workflow_when_adding_assignee_after_demo_is_ready(self):
        slack_messages = self._generate_slack_messages_for_new_ci_status('success')
        self.assertEqual([], slack_messages, 'No message should be sent because no assignees yet')
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@pascal_corpet_reviewer_1 \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['pascal_corpet_reviewer_1']
        )
        self.assertEqual([{
            'slack_channel': '@pascal',
            'slack_message':
                '_@guillaume needs your help to review their change ' +
                '<https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|Fixed some bug>:_\n' +
                "Let's <https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|check this code>!"
        }], slack_messages)

    def test_error_message_when_assigned_to_unknown_user(self):
        slack_messages = self._generate_slack_messages_for_new_ci_status('success')
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@gandalf \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['gandalf']
        )
        self.assertEqual(['#general'], [message.get('slack_channel') for message in slack_messages])
        self.assertTrue(slack_messages[0]['slack_message'].startswith(
            "Error: Need to add Github user 'gandalf' to GITHUB_TO_SLACK_LOGIN"
        ))

if __name__ == '__main__':
    unittest.main()  # pragma: no cover
