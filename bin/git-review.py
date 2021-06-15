#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
Pushes the current branch to the remote repository,
naming the remote branch with a user-specific prefix,
and creates a pull/merge request (depending whether on GitHub or GitLab)
with the specified reviewers (if any).
"""

import argparse
import datetime
import functools
import getpass
from html import parser
import json
import logging
import os
import platform
import re
import subprocess
import sys
import time
import typing
from typing import Any, Callable, Dict, List, Literal, NoReturn, Optional, Set, Tuple, TypedDict
import unicodedata

try:
    import requests
    from requests import exceptions

    class LuccaSession(requests.Session):
        """A connected session to the Lucca API."""

        def __init__(
                self, base_url: str, token: Optional[str], *,
                on_refresh: Callable[['LuccaSession'], None]) -> None:
            super().__init__()
            self._base_url = base_url
            if token:
                self.cookies.set('authToken', token)
            self._on_refresh = on_refresh

        def get(self, url: str, *args: Any, **kwargs: Any) -> requests.Response:
            url = f'{self._base_url}/{url}'
            try:
                response = super().get(url, *args, **kwargs)
                response.raise_for_status()
                return response
            except exceptions.HTTPError:
                LoginHTMLParser('identity/login', self).\
                    get_token(input('Lucca login:'), getpass.getpass())
                self._on_refresh(self)
            return super().get(url, *args, **kwargs)

        def get_today_ooos(self) -> Set[str]:
            """List the email addresses of people being OoO this half-day."""

            today = datetime.datetime.now()
            day = today.date().isoformat()
            is_am = today.hour <= 12
            response = self.get('api/v3/leaves', params={
                'date': day,
                'fields': 'leavePeriod[owner[mail]]',
                'isAM': is_am,
                'leavePeriod.owner.departmentId': 1,
            })
            response.raise_for_status()
            return {
                item['leavePeriod']['owner']['mail'] for item in response.json()['data']['items']}
except ImportError:
    requests = None
    LuccaSession = None  # pylint: disable=invalid-name
try:
    import argcomplete
except ImportError:
    # This is not needed for the script to work.
    argcomplete = None
try:
    import gitlab
except ImportError:
    # This is not needed when pushing to a Github repo.
    gitlab = None

# TODO(cyrille): Lint, type and test.

# Name of the remote to which the script pushes.
_REMOTE_REPO = 'origin'
# Slugged name for the Bayes Impact Github engineering team.
_GITHUB_ENG_TEAM_SLUG = 'software-engineers'

_ONE_DAY = 86400
_TEN_MINUTES = 600
_ONE_MINUTE = 60
# Separation regex for a comma separated list.
_COMMA_SEPARATION_REGEX = re.compile(r'\s*,\s*')
# Chars we want to avoid in branch names.
_FORBIDDEN_CHARS_REGEX = re.compile(r'[#\u0300-\u036f]')
# Remote URL pattern for Gitlab repos.
_GITLAB_URL_REGEX = re.compile(r'^git@gitlab\.com:(.*)\.git')
# Remote URL pattern for Github repos.
_GITHUB_URL_REGEX = re.compile(r'^git@github\.com:(.*)\.git')
# Word pattern, for slugging.
_WORD_REGEX = re.compile(r'\w+')
# Default value for the browse action.
_BROWSE_CURRENT = '__current__browse__'

# TODO(cyrille): Add blame mode.
_AutoEnum = Literal['round-robin']
_AutoEnumValues: Tuple[_AutoEnum, ...] = ('round-robin',)

_CACHE_BUSTER: List[str] = []


class _GitlabMRRequest(TypedDict, total=False):
    description: str
    source_branch: str
    target_branch: str
    title: str
    assignee_ids: List[int]


class _ScriptError(ValueError):

    def __init__(self, msg: str, *args: Any) -> None:
        super().__init__(msg % args if args else msg)
        self._stable_message = msg

    def __hash__(self) -> int:
        return sum((ord(char) - 64) * 53 ** i for i, char in enumerate(self._stable_message))


def _run_git(command: List[str], **kwargs: Any) -> str:
    return subprocess.check_output(['git'] + command, text=True, **kwargs).strip()


def _has_git_diff(base: str) -> bool:
    return bool(subprocess.run(['git', 'diff', '--quiet', base]).returncode)


# TODO(cyrille): Use tuples rather than lists.
def _run_hub(command: List[str], *, cache: Optional[int] = None, **kwargs: Any) -> str:
    final_command = ['hub'] + command
    if cache and not _CACHE_BUSTER:
        final_command.extend(['--cache', str(cache)])
    return subprocess.check_output(final_command, text=True, **kwargs).strip()


_GithubAPIReference = TypedDict('_GithubAPIReference', {'ref': str})
_GithubAPIUser = TypedDict('_GithubAPIUser', {'login': str})


class _GithubAPIPullRequest(TypedDict, total=False):
    base: _GithubAPIReference
    head: _GithubAPIReference
    number: int
    requested_reviewers: List[_GithubAPIUser]


class _GithubPullRequest(typing.NamedTuple):
    base: str
    head: str
    number: int
    reviewers: Set[str]

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def fetch_all() -> List['_GithubPullRequest']:
        """Get all pull requests for the current repository."""

        all_prs = typing.cast(List[_GithubAPIPullRequest], json.loads(
            _run_hub(['api', r'/repos/{owner}/{repo}/pulls'], cache=_ONE_MINUTE)))
        return [
            _GithubPullRequest(
                pr['base']['ref'], pr['head']['ref'], pr['number'],
                {rev['login'] for rev in pr['requested_reviewers']})
            for pr in all_prs]


class LoginHTMLParser(parser.HTMLParser):
    """Parse the login HTML page, and fill its form with login info to get an auth token."""

    def __init__(self, login_url: str, session: 'requests.Session') -> None:
        super().__init__()
        self._login_url = login_url
        self._in_form = False
        self._form: Dict[str, str] = {}
        self._session = session
        self.feed(self._session.get(login_url).text)

    def handle_starttag(self, tag, attrs) -> None:
        if tag == 'form':
            self._in_form = True
            return
        if tag == 'input' and self._in_form:
            attr_dict = dict(attrs)
            if 'name' in attr_dict and 'value' in attr_dict:
                self._form[attr_dict['name']] = attr_dict['value']

    def handle_endtag(self, tag) -> None:
        if tag == 'form':
            self._in_form = False

    def get_token(self, username: str, password: str) -> str:
        """Get token from login information."""

        if not self._form:
            raise ValueError(f"The parsed HTML at {self._login_url} didn't contain a useful form")
        response = self._session.post(
            'https://bayesimpact.ilucca.net/identity/login',
            data=dict(self._form, UserName=username, Password=password, IsPersistent=True))
        response.raise_for_status()
        return self._session.cookies.get('authToken')


class _GitConfig:

    def get_config(self, key: str, *, is_global: bool = False) -> str:
        """Get a config value from git."""

        return _run_git(
            ['config', '--default', ''] + (['--global'] if is_global else []) + ['--get', key])

    def set_config(self, key: str, value: str, *, is_global: bool = False) -> None:
        """Set a config value to git."""

        _run_git(['config'] + (['--global'] if is_global else []) + [key, value])

    @property
    def engineers_team_id(self) -> str:
        """ID for the engineers team."""

        value = self.get_config('review.engineers')
        if not value:
            value = str(_get_platform().get_engineers_team_id())
            self.engineers_team_id = value
        return value

    @engineers_team_id.setter
    def engineers_team_id(self, value: str) -> None:
        self.set_config('review.engineers', value)

    @property
    def recent_reviewers(self) -> List[str]:
        """List of reviewers, starting with the most recently used ones."""

        return self.get_config('review.recent', is_global=True).split(',')

    @recent_reviewers.setter
    def recent_reviewers(self, reviewers: List[str]) -> None:
        """Update the list of most recent reviewers."""

        self.set_config('review.recent', ','.join(r for r in reviewers if r), is_global=True)

    @property
    def lucca_url(self) -> str:
        """A base URL for Lucca API."""

        value = self.get_config('review.lucca.url', is_global=True)
        if not value:
            value = 'https://bayesimpact.ilucca.net'
            self.lucca_url = value
        return value

    @lucca_url.setter
    def lucca_url(self, url: str) -> None:
        self.set_config('review.lucca.url', url, is_global=True)

    @property
    def lucca_session(self) -> Optional['LuccaSession']:
        """Value for a valid token for Lucca API."""

        if not requests or not LuccaSession:
            if not os.getenv('GIT_REVIEW_DISABLE_REQUESTS_WARNING'):
                logging.warning(
                    'Install requests if you want to link your reviews to Lucca.\n'
                    'You can disable this warning by setting GIT_REVIEW_DISABLE_REQUESTS_WARNING=1')
            return None
        base_url = self.lucca_url
        if not base_url:
            return None
        token = self.get_config('review.lucca.token', is_global=True)
        session = LuccaSession(
            base_url, token, on_refresh=lambda s: setattr(self, 'lucca_session', s))
        return session

    @lucca_session.setter
    def lucca_session(self, value: 'LuccaSession') -> None:
        """Update the saved Lucca token."""

        self.set_config('review.lucca.token', value.cookies.get('authToken'), is_global=True)


_GIT_CONFIG = _GitConfig()


class _References(typing.NamedTuple):
    """Simple structure containing all needed branch references."""

    # Default branch on the remote repository.
    default: str
    # Local branch to push and review.
    branch: str
    # Remote name for the reviewed branch.
    remote: str
    # Remote branch onto which the changes should be merged.
    base: str


# TODO(cyrille): Consider uncaching.
@functools.lru_cache()
def _get_head() -> str:
    if branch := _run_git(['rev-parse', '--abbrev-ref', 'HEAD']):
        return branch
    raise _ScriptError('Unable to find a branch at HEAD')


@functools.lru_cache()
def _get_default() -> str:
    try:
        return _run_git(['rev-parse', '--abbrev-ref', f'{_REMOTE_REPO}/HEAD']).split('/')[1]
    except subprocess.CalledProcessError as error:
        raise _ScriptError(
            'Unable to find a remote HEAD reference.\n'
            f'Please run `git remote set-head {_REMOTE_REPO} -a` and rerun your command.'
        ) from error


@functools.lru_cache()
def _get_existing_remote() -> Optional[str]:
    if remote := _GIT_CONFIG.get_config(f'branch.{_get_head()}.merge'):
        return remote[len('refs.heads.'):]
    return None


def _create_branch_for_review() -> Optional[str]:
    _run_git(['fetch'])
    merge_base = _run_git(['merge-base', 'HEAD', 'origin/HEAD'])
    if not _has_git_diff(merge_base):
        # No new commit to review.
        return None
    title = _run_git(['log', '-1', r'--format=%s'])
    # Create a clean branch name from the first two words of the commit message.
    branch = '-'.join(
        word.lower()
        for word in _WORD_REGEX.findall(_cleanup_branch_name(title).replace('_', '-'))[:2])
    branch += f'-{int(time.time()):d}'
    _run_git(['checkout', '-b', branch])
    _run_git(['checkout', '-'])
    _run_git(['reset', '--hard', merge_base])
    _run_git(['checkout', '-'])
    _get_head.cache_clear()
    return branch


def _get_git_branches(username: str, base: Optional[str]) -> _References:
    """Compute the different branch names that will be needed throughout the script."""

    if _has_git_diff('HEAD'):
        raise _ScriptError(
            'Current git status is dirty. '
            'Commit, stash or revert your changes before sending for review.')
    branch = _get_head()
    default = _get_default()
    if branch == default:
        # TODO(cyrille): Add --new for side branches too.
        new_branch = _create_branch_for_review()
        if not new_branch:
            # List branches in user-preferred order, without the asterisk on current branch.
            all_branches = _run_git(['branch', '--format=%(refname:short)']).split('\n')
            all_branches.remove(default)
            raise _ScriptError('branch required:\n\t%s', '\n\t'.join(all_branches))
        branch = new_branch

    remote_branch = _get_existing_remote() or _cleanup_branch_name(f'{username}-{branch}')

    if not base:
        base = _get_best_base_branch(branch, remote_branch, default) or default

    return _References(default, branch, remote_branch, base)


def _get_best_base_branch(branch: str, remote: str, default: str) -> Optional[str]:
    """Guess on which branch the changes should be merged."""

    remote_branches: Optional[str] = None
    for sha1 in _run_git(['rev-list', '--max-count=5', branch]).split('\n')[1:]:
        if remote_branches := _run_git(
                ['branch', '-r', '--contains', sha1, '--list', f'{_REMOTE_REPO}/*']):
            break
    else:
        return None
    if any(rb.endswith(f'/{default}') for rb in remote_branches.split('\n')):
        return None
    for remote_branch in remote_branches.split('\n'):
        base = remote_branch.rsplit('/', 1)[-1]
        if base != remote:
            return base
    return None


def _cleanup_branch_name(branch: str) -> str:
    """Avoid unwanted characters in branche names."""

    return _FORBIDDEN_CHARS_REGEX.sub('', unicodedata.normalize('NFD', branch))


def _push(refs: _References, is_forced: bool) -> None:
    """Push the branch to the remote repository."""

    command = ['push']
    if is_forced:
        command.append('-f')
    command.extend(['-u', _REMOTE_REPO, f'{refs.branch}:{refs.remote}'])
    _run_git(command)


def _make_pr_message(refs: _References, reviewers: List[str]) -> str:
    """Create a message for the review request."""

    return _run_git(['log', '--format=%B', f'{_REMOTE_REPO}/{refs.base}..{refs.branch}']) + \
        _run_git_review_hook(refs.branch, refs.remote, reviewers)


def _run_git_review_hook(branch: str, remote_branch: str, reviewers: List[str]) -> str:
    """Run the git-review hook if it exists."""

    hook_script = f'{_run_git(["rev-parse", "--show-toplevel"])}/.git-review-hook'
    if not os.access(hook_script, os.X_OK):
        return ''
    return subprocess.check_output(hook_script, text=True, env=dict(os.environ, **{
        'BRANCH': branch,
        'REMOTE_BRANCH': remote_branch,
        'REVIEWER': ','.join(reviewers),
    }))


class _RemoteGitPlatform:

    _platform: str

    def __init__(self, project_name: str) -> None:
        self.project_name = project_name

    @staticmethod
    def from_url(remote_url: str) -> '_RemoteGitPlatform':
        """Factory for subclasses depending on URL regex."""

        if gitlab_match := _GITLAB_URL_REGEX.match(remote_url):
            return _GitlabPlatform(gitlab_match[1])
        if github_match := _GITHUB_URL_REGEX.match(remote_url):
            return _GithubPlatform(github_match[1])
        raise NotImplementedError(f'Review platform not recognized. Remote URL is {remote_url}')

    def get_engineers_team_id(self) -> int:
        """Find an ID that references the engineering team on this platform."""

        logging.warning('No engineering team set for this platform')
        return ''

    @property
    def engineers(self) -> Set[str]:
        """List of possible engineer reviewers."""

        return set()

    def request_review(self, refs: _References, reviewers: List[str]) -> None:
        """Ask for a review on the specific platform."""

        message = None if self._has_existing_review(refs) else _make_pr_message(refs, reviewers)
        self._request_review(refs, reviewers, message)
        if reviewers:
            # Remove duplicates while preserving ordering.
            recents = list(dict.fromkeys(reviewers + _GIT_CONFIG.recent_reviewers))
            _GIT_CONFIG.recent_reviewers = recents
        self.add_review_label(refs.branch)

    def add_review_label(self, branch: str) -> None:
        """Mark all references issues as 'in review'."""

        commit_msg = _run_git(['log', branch, '-1', r'--format=%B'])
        issues = {
            issue.lstrip('#')
            for line in commit_msg.split('\n')
            if line.startswith('Fix ')
            for issue in _COMMA_SEPARATION_REGEX.split(line[len('Fix '):])
            if issue.startswith('#')}
        for issue in issues:
            self._add_label(issue, '[zube]: In Review')

    def _add_label(self, issue_number: str, label: str) -> None:
        raise self._not_implemented('git review', ' Zube interop')

    def _has_existing_review(self, refs) -> bool:
        return self._get_review_number(refs.remote) is not None

    def _not_implemented(self, command: str, context: str = '') -> NoReturn:
        raise NotImplementedError(
            f'`{command}`{context} is not implemented for {self._platform} yet.')

    def _request_review(self, refs: _References, reviewers: List[str], message: Optional[str]) \
            -> None:
        self._not_implemented('git review')

    def get_available_reviewers(self) -> Set[str]:
        """List the possible values for reviewers."""

        self._not_implemented('git review', ' autocomplete')

    def _get_review_number(self, branch: str, base: Optional[str] = None) -> Optional[str]:
        self._not_implemented('git review --browse')

    def get_review_url_for(self, branch: Optional[str]) -> str:
        """Give the URL where one can review the code on the given branch."""

        number = None if not branch else self._get_review_number(branch)
        if not number:
            raise _ScriptError('No opened review for branch "%s".', branch)
        return f'https://reviewable.io/reviews/{self.project_name}/{number}'

    def get_available_reviews(self) -> List[str]:
        """List branches the user should review."""

        self._not_implemented('git review --browse', ' autocomplete')


class _GitlabPlatform(_RemoteGitPlatform):

    _platform = 'Gitlab'

    def __init__(self, project_name: str) -> None:
        super().__init__(project_name)
        if not gitlab:
            raise _ScriptError(
                'gitlab tool is not installed, please install it:\n'
                '  https://github.com/bayesimpact/bayes-developer-setup/blob/HEAD/gitlab-cli.md')
        self.client = gitlab.Gitlab.from_config()
        self.project = self.client.projects.get(project_name)

    @property
    def engineers(self) -> Set[str]:
        """Set of Gitlab handles for the engineers."""

        logging.warning('No engineers team set-up for Gitlab. Not assigning anyone.')
        return set()

    def _get_reviewers(self, reviewers: List[str]) -> List[int]:
        return [user.id for r in reviewers for user in self.client.users.list(username=r)]

    def _get_merge_request(self, branch: str, base: Optional[str]) \
            -> Optional['gitlab.MergeRequest']:
        return next((
            mr for mr in self.project.merge_request.list()
            if mr.source_branch == branch
            if not base or mr.target_branch == base), None)

    def _get_review_number(self, branch: str, base: Optional[str] = None) -> Optional[str]:
        if merge_request := self._get_merge_request(branch, base):
            return merge_request.number
        return None

    def _request_review(self, refs: _References, reviewers: List[str], message: Optional[str]) \
            -> None:
        users = self._get_reviewers(reviewers)
        if not message:
            if not users:
                return
            if merge_request := self._get_merge_request(refs.remote, refs.base):
                merge_request.assignee_ids.extend(users)
                merge_request.save()
            return
        title, description = message.split('\n', 1)
        mr_parameters: _GitlabMRRequest = {
            'assignee_ids': users,
            'description': description,
            'source_branch': refs.remote,
            'target_branch': refs.base,
            'title': title,
        }
        self.project.merge_request.create(mr_parameters)

    def get_available_reviewers(self) -> Set[str]:
        return {member.username for member in self.project.members.list()}


class _GithubPlatform(_RemoteGitPlatform):

    _platform = 'Github'

    def __init__(self, project_name: str) -> None:
        super().__init__(project_name)
        try:
            _run_hub(['browse', '-u'])
        except subprocess.CalledProcessError as error:
            raise _ScriptError(
                'hub tool is not installed, or wrongly configured.\n'
                'Please install it with ~/.bayes-developer-setup/install.sh') from error

    @property
    def engineers(self) -> Set[str]:
        """Set of Github handles for the engineers."""

        if not _GIT_CONFIG.engineers_team_id:
            logging.warning(
                'The engineering team Github ID is not in your environment. '
                'Please run install.sh.')
            return set()
        members = json.loads(
            _run_hub(['api', f'/teams/{_GIT_CONFIG.engineers_team_id}/members'], cache=_ONE_DAY))
        return {member['login'] for member in members} - {self.username}

    def get_engineers_team_id(self) -> int:
        return json.loads(_run_hub(
            ['api', f'/orgs/bayesimpact/teams/{_GITHUB_ENG_TEAM_SLUG}'], cache=_ONE_DAY))['id']

    def _add_label(self, issue_number: str, label: str) -> None:
        _run_hub([
            'api', r'/repos/{owner}/{repo}/issues/'
            f'{issue_number}/labels', '--input', '-',
        ], input=json.dumps({'labels': [label]}))

    def _add_reviewers(self, refs: _References, reviewers: List[str]) -> None:
        """Add reviewers to the current Pull Request."""

        if not reviewers:
            return
        pull_number = self._get_review_number(refs.remote, refs.base)
        requested_reviewers = set(reviewers) & self.engineers
        assignees = set(reviewers) - self.engineers
        _run_hub([
            'api', r'/repos/{owner}/{repo}/pulls/'
            f'{pull_number}/requested_reviewers',
            '--input', '-',
        ], input=json.dumps({'reviewers': list(requested_reviewers)}))
        _run_hub([
            'api', r'/repos/{owner}/{repo}/issues/'
            f'{pull_number}/assignees',
            '--input', '-',
        ], input=json.dumps({'assignees': list(assignees)}))

    def _request_review(self, refs: _References, reviewers: List[str], message: Optional[str]) \
            -> None:
        """Ask for review on Github."""

        if not message:
            self._add_reviewers(refs, reviewers)
            return
        hub_command = [
            'pull-request',
            '-m', message,
            '-h', refs.remote,
            '-b', refs.base]
        if reviewers:
            if self.engineers:
                requested_reviewers = set(reviewers) & self.engineers
                assignees = set(reviewers) - self.engineers
            else:
                assignees = requested_reviewers = set(reviewers)
            hub_command.extend(['-a', ','.join(assignees), '-r', ','.join(requested_reviewers)])
        output = _run_hub(hub_command)
        logging.info(output.replace('github.com', 'reviewable.io/reviews').replace('pull/', ''))

    def get_available_reviewers(self) -> Set[str]:
        assignees = json.loads(_run_hub(
            ['api', r'repos/{owner}/{repo}/assignees'], cache=_TEN_MINUTES))
        return {assignee.get('login', '') for assignee in assignees} - {'', self.username}

    def _get_review_number(self, branch: str, base: Optional[str] = None) -> Optional[str]:
        return next((
            str(pr.number) for pr in _GithubPullRequest.fetch_all()
            if pr.head == branch
            if not base or pr.base == base), None)

    @functools.cached_property
    def username(self) -> str:
        """The handle for the current Github user."""

        with open(f'{os.getenv("HOME")}/.config/hub') as hub_config:
            user_line = next(line for line in hub_config.readlines() if 'user' in line)
        return user_line.split(':')[1].strip()

    def get_available_reviews(self) -> List[str]:
        return [
            pr.head
            for pr in _GithubPullRequest.fetch_all()
            if self.username in pr.reviewers]


@functools.lru_cache()
def _get_platform() -> _RemoteGitPlatform:
    """Get the relevant review platform once and for all."""

    return _RemoteGitPlatform.from_url(_GIT_CONFIG.get_config(f'remote.{_REMOTE_REPO}.url'))


def _ask_for_email(potential: str) -> str:
    potential_email = input(
        f'Please, enter the professional email for "{potential}".\n'
        'It should end with `@bayesimpact.org`.')
    if potential_email:
        _GIT_CONFIG.set_config(f'review.lucca.{potential}', potential_email, is_global=True)
    return potential_email


def _remove_absents(available: Set[str]) -> Set[str]:
    absents: Set[str] = set()
    if session := _GIT_CONFIG.lucca_session:
        absents = session.get_today_ooos()
    if not absents:
        return available
    for potential in set(available):
        potential_email = _GIT_CONFIG.get_config(f'review.lucca.{potential}', is_global=True)
        if not potential_email:
            potential_email = _ask_for_email(potential)
        if potential_email in absents:
            available -= {potential}
    return available


def _get_auto_reviewer(auto: _AutoEnum) -> str:
    if auto == 'round-robin':
        available = _remove_absents(set(_get_platform().engineers))
        if not available:
            raise _ScriptError('Unable to auto-assign a reviewer.')
        recents = _GIT_CONFIG.recent_reviewers
        for recent in recents:
            available = available - {recent}
            if not available:
                return recent
        return next(iter(available))


def prepare_push_and_request_review(
        *, username: str, base: Optional[str], reviewers: List[str],
        is_submit: bool, auto: _AutoEnum) -> None:
    """Prepare a local Change List for review."""

    if not username:
        raise _ScriptError(
            'Could not find username, most probably you need to setup an email with:\n'
            '  git config user.email <me@bayesimpact.org>')
    refs = _get_git_branches(username, base)
    merge_base = _run_git(['merge-base', 'HEAD', f'{_REMOTE_REPO}/{refs.base}'])
    if _has_git_diff(merge_base):
        _push(refs, _get_existing_remote() == refs.remote)
    if auto:
        reviewer = _get_auto_reviewer(auto)
        logging.info('Sending the review to "%s".', reviewer)
        reviewers = [reviewer]
    _get_platform().request_review(refs, reviewers)
    if not is_submit:
        return
    local_sha = _run_git(['rev-parse', refs.branch])
    remote_sha = _run_git(['rev-parse', f'{_REMOTE_REPO}/{refs.remote}'])
    if local_sha != remote_sha:
        raise _ScriptError(
            'Local branch is not in the same state as remote branch. Not submitting.')
    _run_git(['submit'], env=dict(os.environ, GIT_SUBMIT_AUTO_MERGE='1'))


def _get_default_username(username: str) -> str:
    if username:
        return username
    if email := _GIT_CONFIG.get_config('user.email'):
        return email.split('@')[0]
    raise _ScriptError('Please, set your email in git config.')


def _browse_to(branch: str) -> None:
    real_branch = _get_existing_remote() or _get_head() if branch == _BROWSE_CURRENT else branch
    url = _get_platform().get_review_url_for(real_branch or branch)
    open_command = 'open' if platform.system() == 'Darwin' else 'xdg-open'
    subprocess.check_output([open_command, url])


def main(string_args: Optional[List[str]] = None) -> None:
    """Parse CLI arguments and run the script."""

    # TODO(cyrille): Do not auto-complete on mutually exclusive args (reviewers, auto, browse).
    parser = argparse.ArgumentParser(description='Start a review for your change list.')
    parser.add_argument(
        'reviewers',
        help='Github handles of the reviewers you want to assign to your review.', nargs='*',
    ).completer = lambda **kw: _get_platform().get_available_reviewers()
    parser.add_argument(
        '-a', '--auto', choices=_AutoEnumValues, help='''
            Let the program choose an engineer to review for you.''',
        nargs='?', const=_AutoEnumValues[0])
    parser.add_argument(
        '-f', '--force', action='store_true', help='''
            [DEPRECATED]: The script now determines whether the push should be forced or not.''',
    ).completer = argcomplete and argcomplete.SuppressCompleter()
    parser.add_argument('-s', '--submit', action='store_true', help='''
        Ask GitHub to auto-merge the branch, when all conditions are satisfied.
        Runs 'git submit'.''')
    parser.add_argument('-u', '--username', type=_get_default_username, default='', help='''
        Set the prefix for the remote branch to USER.
        Default is username from the git user's email (such as in username@example.com)''')
    # TODO(cyrille): Auto-complete.
    parser.add_argument('-b', '--base', help='''
        Force the pull/merge request to be based on the given base branch on the remote.''')
    parser.add_argument('--no-cache', dest='cache', action='store_false', help='''
        Clear the cache mechanism on hub API calls.''')
    parser.add_argument(
        '--browse', help='''
        Open the review in a browser window.
        Defaults to the remote branch attached to the current branch.''',
        nargs='?', const=_BROWSE_CURRENT,
    ).completer = lambda **kw: _get_platform().get_available_reviews()
    if argcomplete:
        argcomplete.autocomplete(parser)
    args = parser.parse_args(string_args)
    # TODO(cyrille): Update log level depending on required verbosity.
    logging.basicConfig(level=logging.INFO)
    if not args.cache:
        _CACHE_BUSTER.append('busted')
    if args.force:
        logging.warning(
            'The --force (-f) option is now deprecated. '
            'The force option of the push is now determined by the current git state.')
    if args.browse:
        _browse_to(args.browse)
        return
    prepare_push_and_request_review(
        username=args.username, base=args.base, reviewers=args.reviewers,
        is_submit=args.submit, auto=args.auto)


if __name__ == '__main__':
    try:
        main()
    except _ScriptError as error:
        print(error)
        # TODO(cyrille): Make sure that those are distinct.
        sys.exit(hash(error))
