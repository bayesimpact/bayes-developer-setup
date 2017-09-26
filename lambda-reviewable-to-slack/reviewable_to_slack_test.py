"""Tests for the integration between Reviewable/Github webhooks and Slack."""
import unittest

import mock

from reviewable_to_slack import generate_slack_messages

_ERROR_SLACK_CHANNEL = '#general'
_GITHUB_TO_SLACK_LOGIN = {
    'guillaume_chaslot_reviewee': 'guillaume',
    'pascal_corpet_reviewer_1': 'pascal',
    'john_metois_reviewer_2': 'john',
    # User who gave their personal token to Reviewable to write 'demo is ready'
    'florian_jourda_circle_ci': 'florian',
}


class ReviewableToSlackTestCase(unittest.TestCase):
    """Unit tests for the integration between Reviewable notification and Slack."""

    def setUp(self):
        self.maxDiff = None  # pylint: disable=invalid-name
        # State simulating what is present on Github. This will be updated by
        # _simulate_notification_for_new_comment to simulate scenarios, which will
        # change what requests.get on Github API returns.
        self._github_issue = {
            'repository_url': 'https://api.github.com/repos/bayesimpact/bob-emploi',
            'comments_url':
                'https://api.github.com/repos/bayesimpact/bob-emploi/issues/5670/comments',
            'number': 5670,
            'title': 'Fixed some bug',
            'user': {'login': 'guillaume_chaslot_reviewee'},
            'assignees': [],
        }
        self._github_issue_assignee_logins = set()
        # Comments are not given directly inside the issue json in the Github API.
        self._github_issue_comments = []

        # Patch applied to all tests
        self._requests_get_patcher = mock.patch('requests.get')
        mock_requests_get = self._requests_get_patcher.start()
        self.addCleanup(self._requests_get_patcher.stop)
        # We change requests.get to return the simulated state of the Github issue.
        self._make_requests_return_state(mock_requests_get)

        self._github_to_slack_login_patcher = mock.patch(
            'reviewable_to_slack._GITHUB_TO_SLACK_LOGIN', _GITHUB_TO_SLACK_LOGIN)
        self._github_to_slack_login_patcher.start()
        self.addCleanup(self._github_to_slack_login_patcher.stop)

        self._error_slack_channel_patcher = mock.patch(
            'reviewable_to_slack._ERROR_SLACK_CHANNEL', _ERROR_SLACK_CHANNEL)
        self._error_slack_channel_patcher.start()
        self.addCleanup(self._error_slack_channel_patcher.stop)

        super(ReviewableToSlackTestCase, self).setUp()

    def _make_requests_return_state(self, mock_requests_get):
        """Change request.get so that it returns the current state of the Github issue."""
        # TODO(florian): Check the 'auth'
        def _requests_get_side_effect(url, **unused_kwargs):
            """Return the current state of the Github issue."""
            response = mock.MagicMock()
            url_to_response = {
                'https://api.github.com/repos/bayesimpact/bob-emploi/issues/5670/comments':
                    self._github_issue_comments,
            }
            # Will fail if url is not defined in mocked_calls.
            response.json.return_value = url_to_response[url]
            response.status_code = 200
            return response
        mock_requests_get.side_effect = _requests_get_side_effect

    def _simulate_notification_for_new_comment(  # pylint: disable=invalid-name
            self,
            commentor_github_login,
            comment_body,
            new_assignee_github_logins=None):
        """Create a new comment in the Github issue and create Github notification."""
        comment = {
            'user': {'login': commentor_github_login},
            'body': comment_body,
        }
        self._github_issue_assignee_logins.update(new_assignee_github_logins or [])
        self._github_issue['assignees'] = [
            {'login': github_login}
            for github_login in self._github_issue_assignee_logins
        ]
        # The value of _github_issue_comments will be given back by the mocked API call
        # that gets Github comments.
        self._github_issue_comments.append(comment)
        github_notification = {
            'action': 'created',
            'comment': comment,
            'issue': self._github_issue,
        }
        return github_notification

    def _generate_slack_messages_for_new_comment(
            self,
            commentor_github_login,
            comment_body,
            new_assignee_github_logins=None):
        """Get the Slack messages that would be generate when a new Github comment is create."""
        github_notification = self._simulate_notification_for_new_comment(
            commentor_github_login,
            comment_body,
            new_assignee_github_logins)
        slack_messages = generate_slack_messages(github_notification)
        return slack_messages

    # As the name of the tests are self-explanatory, we don't need docstrings for them
    # pylint: disable=missing-docstring
    def test_review_workflow_when_adding_assignee_before_demo_is_ready(self):
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@pascal_corpet_reviewer_1 \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['pascal_corpet_reviewer_1']
        )
        self.assertEqual({}, slack_messages,
                         'No message should be sent because the demo not is ready yet')
        slack_messages = self._generate_slack_messages_for_new_comment(
            'florian_jourda_circle_ci',
            'No demo to review for this commit',
        )
        self.assertEqual({
            '@pascal':
                '_@guillaume needs your help to review their change ' +
                '<https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|Fixed some bug>:_\n' +
                "Let's <https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|check this code>!"  # nopep8 # pylint: disable=line-too-long
        }, slack_messages)

    def test_review_workflow_when_adding_assignee_after_demo_is_ready(self):
        slack_messages = self._generate_slack_messages_for_new_comment(
            'florian_jourda_circle_ci',
            'No demo to review for this commit',
        )
        self.assertEqual({}, slack_messages,
                         'No message should be sent because no assignees yet')
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@pascal_corpet_reviewer_1 \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['pascal_corpet_reviewer_1']
        )
        self.assertEqual({
            '@pascal':
                '_@guillaume needs your help to review their change ' +
                '<https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|Fixed some bug>:_\n' +
                "Let's <https://reviewable.io/reviews/bayesimpact/bob-emploi/5670|check this code>!"  # nopep8 # pylint: disable=line-too-long
        }, slack_messages)

    def test_error_message_when_assigned_to_unknown_user(self):
        slack_messages = self._generate_slack_messages_for_new_comment(
            'florian_jourda_circle_ci',
            'No demo to review for this commit',
        )
        slack_messages = self._generate_slack_messages_for_new_comment(
            'guillaume_chaslot_reviewee',
            '+@gandalf \n\n---\n\nReview status: 0 of 2 files reviewed at latest revision, all discussions resolved.\n\n---\n\n\n\n*Comments from [Reviewable](https://reviewable.io:443/reviews/bayesimpact/bob-emploi/5670#-:-KusZEAfCXr76VdJBPDn:bv2wshd)*\n<!-- Sent from Reviewable.io -->\n',  # nopep8 # pylint: disable=line-too-long
            ['gandalf']
        )
        self.assertEqual({'#general'}, slack_messages.keys())
        self.assertTrue(slack_messages['#general'].startswith(
            "Error: Need to add Github user 'gandalf' to GITHUB_TO_SLACK_LOGIN"
        ), slack_messages['#general'])

if __name__ == '__main__':
    unittest.main()  # pragma: no cover
