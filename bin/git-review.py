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
from html import parser as html_parser
import itertools
import json
import logging
import os
from os import path
import platform
import re
import subprocess
import sys
import typing
from typing import Any, Callable, Dict, List, NoReturn, Optional, Sequence, Set, TypedDict, Union
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

        def get(
                self, url: str, *,
                params: Optional[dict[str, Union[str, int]]] = None) -> requests.Response:
            url = f'{self._base_url}/{url}'
            try:
                response = super().get(url, params=params)
                response.raise_for_status()
                return response
            except exceptions.HTTPError:
                LoginHTMLParser('identity/login', self).\
                    get_token(input('Lucca login:'), getpass.getpass())
                self._on_refresh(self)
            return super().get(url, params=params)

        def get_ooos_on(self, *, half_day_offset: int = 0) -> set[str]:
            """Find the OoO people in a given number of half-days."""

            day = datetime.datetime.now() + datetime.timedelta(days=half_day_offset / 2)
            date = day.date().isoformat()
            is_am = day.hour < 12

            response = self.get('api/v3/leaves', params={
                'date': date,
                'fields': 'leavePeriod.owner.mail,isAM',
                'leavePeriod.owner.departmentId': 1,
            })
            response.raise_for_status()
            absents = {
                leave_email
                for leave in response.json()['data']['items']
                if leave['isAM'] == is_am
                if (leave_email := leave['leavePeriod']['owner'].get('mail'))}

            response = self.get('api/v3/userDates', params={
                'date': date,
                'fields': 'am.isOff,pm.isOff,owner.mail',
            })
            response.raise_for_status()
            off_days = {
                off_email
                for off_day in response.json()['data']['items']
                if off_day['am' if is_am else 'pm']['isOff']
                if (off_email := off_day['owner'].get('mail'))}
            return absents | off_days
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
# Whether we should print each command before running it (bash xtrace), and the prefix to use.
_XTRACE_PREFIX: list[str] = []
_IFS_REGEX = re.compile(r'[ \n]')

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


def _xtrace(command: Sequence[str]) -> None:
    if not _XTRACE_PREFIX:
        return
    sys.stderr.write(
        f'{_XTRACE_PREFIX[0]} ' +
        ' '.join(
            f"'{word}'" if _IFS_REGEX.search(word) else word
            for word in command
        ) + '\n')


def _run_git(command: List[str], **kwargs: Any) -> str:
    full_command = ['git'] + command
    _xtrace(full_command)
    return subprocess.check_output(full_command, text=True, **kwargs).strip()


def _has_git_diff(base: str) -> bool:
    full_command = ['git', 'diff', '--quiet', base]
    _xtrace(full_command)
    return bool(subprocess.run(full_command).returncode)


# TODO(cyrille): Use tuples rather than lists.
def _run_hub(command: List[str], *, cache: Optional[int] = None, **kwargs: Any) -> str:
    final_command = ['hub'] + command
    if cache and not _CACHE_BUSTER:
        final_command.extend(['--cache', str(cache)])
    _xtrace(final_command)
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


class LoginHTMLParser(html_parser.HTMLParser):
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
        """Get a config value from git. Returns an empty string if nothing is found."""

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
            value = _get_platform().get_engineers_team_id()
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

        if _GIT_CONFIG.get_config('review.lucca.enabled') != 'true':
            return None
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
    # Reference to the merge-base commit between `base` and `branch`.
    merge_base: str


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


def _create_branch_for_review(merge_base: str, username: str) -> Optional[str]:
    _run_git(['fetch'])
    if not _has_git_diff(merge_base):
        # No new commit to review.
        return None
    title = _run_git(['log', '-1', r'--format=%s'])
    # Create a clean branch name from the first two words of the commit message.
    branch = '-'.join(
        word.lower()
        for word in _WORD_REGEX.findall(_cleanup_branch_name(title).replace('_', '-'))[:2])
    prefix = f'{_REMOTE_REPO}/{username}-{branch}'
    suffixes = {
        b[len(prefix):]
        for b in _run_git(['branch', '-r', '--format=%(refname:short)']).split('\n')
        if b.startswith(prefix)}
    if suffixes:
        branch += next(
            f'-{counter:d}'
            for counter in itertools.count()
            if f'-{counter:d}' not in suffixes)
    _run_git(['checkout', '-b', branch])
    _run_git(['checkout', '-'])
    _run_git(['reset', '--hard', merge_base])
    _run_git(['checkout', '-'])
    _get_head.cache_clear()
    return branch


def _get_git_branches(username: str, base: Optional[str], is_new: bool) -> _References:
    """Compute the different branch names that will be needed throughout the script."""

    if _has_git_diff('HEAD'):
        raise _ScriptError(
            'Current git status is dirty. '
            'Commit, stash or revert your changes before sending for review.')
    branch = _get_head()
    default = _get_default()
    remote_branch = _get_existing_remote()
    if not base:
        base = _get_best_base_branch(branch, remote_branch, default) or default
    merge_base = _run_git(['merge-base', 'HEAD', f'{_REMOTE_REPO}/{base}'])
    is_new = is_new or branch == default
    if is_new:
        new_branch = _create_branch_for_review(merge_base, username)
        if new_branch:
            branch = new_branch
        elif branch == default:
            # List branches in user-preferred order, without the asterisk on current branch.
            all_branches = _run_git(['branch', '--format=%(refname:short)']).split('\n')
            all_branches.remove(default)
            raise _ScriptError('branch required:\n\t%s', '\n\t'.join(all_branches))
        else:
            raise _ScriptError('No change to put in a new review.')

    if is_new or not remote_branch:
        remote_branch = _cleanup_branch_name(f'{username}-{branch}')

    return _References(default, branch, remote_branch, base, merge_base)


def _get_best_base_branch(branch: str, remote: Optional[str], default: str) -> Optional[str]:
    """Guess on which branch the changes should be merged."""

    remote_branches: Optional[str] = None
    for sha1 in _run_git(['rev-list', '--max-count=5', branch, '--']).split('\n')[1:]:
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

    message = _run_git(['log', '--format=%B', f'{_REMOTE_REPO}/{refs.base}..{refs.branch}'])
    if hook_message := _run_git_review_hook(refs, reviewers):
        message += f'\n\n{hook_message}'
    return message


def _run_git_review_hook(refs: _References, reviewers: List[str]) -> str:
    """Run the git-review hook if it exists."""

    hook_script = f'{_run_git(["rev-parse", "--show-toplevel"])}/.git-review-hook'
    if not os.access(hook_script, os.X_OK):
        if path.exists(hook_script):
            logging.warning('The git review hook exists but is not executable. Ignoring.')
        return ''
    _xtrace([hook_script])
    try:
        return subprocess.check_output(hook_script, text=True, env=dict(os.environ, **{
            'BRANCH': refs.branch,
            'MERGE_BASE': refs.merge_base,
            'REMOTE_BRANCH': refs.remote,
            'REVIEWER': ','.join(reviewers),
        })).strip()
    except OSError as error:
        logging.error('Unable to run the review hook. Ignoring', exc_info=error)
        return ''


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
        if remote_url.startswith('/'):
            return _LocalPlatform(path.basename(remote_url))
        raise NotImplementedError(f'Review platform not recognized. Remote URL is {remote_url}')

    def get_engineers_team_id(self) -> str:
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

    def get_engineers_team_id(self) -> str:
        return str(json.loads(_run_hub(
            ['api', f'/orgs/bayesimpact/teams/{_GITHUB_ENG_TEAM_SLUG}'], cache=_ONE_DAY))['id'])

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
        assignees = requested_reviewers = set(reviewers)
        if self.engineers:
            requested_reviewers = requested_reviewers & set(self.engineers)
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
            assignees = requested_reviewers = set(reviewers)
            if self.engineers:
                requested_reviewers = requested_reviewers & set(self.engineers)
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

        with open(path.expanduser('~/.config/hub'), encoding='utf-8') as hub_config:
            user_line = next(line for line in hub_config.readlines() if 'user' in line)
        return user_line.split(':')[1].strip()

    def get_available_reviews(self) -> List[str]:
        return [
            pr.head
            for pr in _GithubPullRequest.fetch_all()
            if self.username in pr.reviewers]


class _LocalPlatform(_RemoteGitPlatform):

    _platform = 'local remote'

    def _request_review(self, refs: _References, reviewers: List[str], message: Optional[str]) \
            -> None:
        ...

    def _get_review_number(self, branch: str, base: Optional[str] = None) -> Optional[str]:
        return None


@functools.lru_cache()
def _get_platform() -> _RemoteGitPlatform:
    """Get the relevant review platform once and for all."""

    return _RemoteGitPlatform.from_url(_GIT_CONFIG.get_config(f'remote.{_REMOTE_REPO}.url'))


def _can_review(potential: str, absentee_emails: list[str]) -> bool:
    """Ask if one of the emails is potential's, or if you don't want their review.

    If an email is selected, it saves this email in git config, and returns False.
    Otherwise, returns False if user answered "I don't want them to review this".
    """

    print(f'''No email is set for {potential}. Is one of those their address?''')
    selected = int(subprocess.check_output(
        f'''select email in {' '.join(absentee_emails)} \
          "I don't want them to review this" \
          "None of the above"
        do
          if [ -n "$email" ]; then
            break
          fi
        done
        echo "$REPLY"
        ''', env={'PS3': f"Which is {potential}'s email?"}, shell=True, text=True).strip()) - 1
    try:
        _GIT_CONFIG.set_config(
            f'review.lucca.{potential}', absentee_emails[selected], is_global=True)
        return False
    except IndexError:
        return selected > len(absentee_emails)


def _get_auto_reviewer() -> Optional[str]:
    all_engineers = set(_get_platform().engineers)
    if not all_engineers:
        raise _ScriptError('Unable to auto-assign a reviewer.')
    prioritized_reviewers = [
        r for r in list(dict.fromkeys(_GIT_CONFIG.recent_reviewers + list(all_engineers)))
        if r in all_engineers][::-1]
    if not prioritized_reviewers:
        return None
    if not _GIT_CONFIG.lucca_session:
        return prioritized_reviewers[0]
    for half_day_offset in itertools.count():
        absents = _GIT_CONFIG.lucca_session.get_ooos_on(half_day_offset=half_day_offset)
        for reviewer in prioritized_reviewers:
            reviewer_email = _GIT_CONFIG.get_config(f'review.lucca.{reviewer}')
            if reviewer_email and reviewer_email not in absents:
                return reviewer
            if not reviewer_email and _can_review(reviewer, list(absents)):
                return reviewer
    raise ValueError('This cannot happen.')


def prepare_push_and_request_review(
        *, username: str, base: Optional[str], reviewers: List[str],
        is_submit: bool, is_auto: bool, is_new: bool) -> None:
    """Prepare a local Change List for review."""

    if not username:
        raise _ScriptError(
            'Could not find username, most probably you need to setup an email with:\n'
            '  git config user.email <me@bayesimpact.org>')
    refs = _get_git_branches(username, base, is_new)
    if _has_git_diff(refs.merge_base):
        _push(refs, not is_new and _get_existing_remote() == refs.remote)
    if is_auto:
        reviewer = _get_auto_reviewer()
        logging.info('Sending the review to "%s".', reviewer)
        reviewers.append(reviewer)
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
    _xtrace(open_command)
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
        '-a', '--auto', action='store_true', help='''
            Let the program choose an engineer to review for you.''')
    parser.add_argument(
        '-f', '--force', action='store_true', help='''
            [DEPRECATED]: The script now determines whether the push should be forced or not.''',
    ).completer = argcomplete and argcomplete.SuppressCompleter()
    parser.add_argument(
        '-n', '--new', action='store_true', help='''
            Force to consider the last changes as a new review.
            This is the default when running on the default (main) branch.''',
    )
    parser.add_argument(
        '-x', '--xtrace', help='''
            If set, print all subcommands before running them like the bash xtrace mode. And use
            the given value as a prefix for each line.''')
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
    if args.xtrace:
        del _XTRACE_PREFIX[:]
        _XTRACE_PREFIX.append(args.xtrace)
    if args.browse:
        _browse_to(args.browse)
        return
    prepare_push_and_request_review(
        username=args.username, base=args.base, reviewers=args.reviewers,
        is_submit=args.submit, is_auto=args.auto, is_new=args.new)


if __name__ == '__main__':
    try:
        main()
    except _ScriptError as error:
        print(error)
        # TODO(cyrille): Make sure that those are distinct.
        sys.exit(hash(error))
