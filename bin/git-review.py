#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""
Pushes the current branch to the remote repository,
naming the remote branch with a user-specific prefix,
and creates a pull/merge request (depending whether on GitHub or GitLab)
with the specified reviewers (if any).
"""

import argparse
import functools
import json
import logging
import os
import platform
import re
import subprocess
import sys
import typing
from typing import Any, List, Optional, TypedDict
import unicodedata

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

# Name of the remote to which the script pushes.
_REMOTE_REPO = 'origin'
_FORBIDDEN_CHARS_REGEX = re.compile(r'[#\u0300-\u036f]')
_GITLAB_URL_REGEX = re.compile(r'^git@gitlab\.com:(.*)\.git')
_GITHUB_URL_REGEX = re.compile(r'^git@github\.com:(.*)\.git')
_BROWSE_CURRENT = '__current__browse__'


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


# TODO(cyrille): Use wherever applicable.
def _run_hub(command: List[str], **kwargs: Any) -> str:
    return subprocess.check_output(['hub'] + command, text=True, **kwargs).strip()


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


@functools.lru_cache()
def _get_head() -> str:
    if branch := _run_git(['rev-parse', '--abbrev-ref', 'HEAD']):
        return branch
    raise _ScriptError('Unable to find a branch at HEAD')


@functools.lru_cache()
def _get_default() -> str:
    return _run_git(['rev-parse', '--abbrev-ref', f'{_REMOTE_REPO}/HEAD']).split('/')[1]


@functools.lru_cache()
def _get_existing_remote() -> Optional[str]:
    try:
        return _run_git(['config', f'branch.{_get_head()}.merge'])[len('refs.heads.'):]
    except subprocess.CalledProcessError:
        return None


def _get_git_branches(username: str, base: Optional[str]) -> _References:
    """Compute the different branch names that will be needed throughout the script."""

    branch = _get_head()
    default = _get_default()
    if branch == default:
        # List branches in user-preferred order, without the asterisk on current branch.
        all_branches = _run_git(['branch', '--format=%(refname:short)']).split('\n')
        all_branches.remove(default)
        raise _ScriptError('branch required:\n\t%s', '\n\t'.join(all_branches))
    if _has_git_diff('HEAD'):
        raise _ScriptError(
            'Current git status is dirty. '
            'Commit, stash or revert your changes before sending for review.')

    if not base:
        base = _get_best_base_branch(branch, default) or default

    remote_branch = _get_existing_remote() or _cleanup_branch_name(f'{username}-{branch}')

    return _References(default, branch, remote_branch, base)


def _get_best_base_branch(branch: str, default: str) -> Optional[str]:
    """Guess on which branch the changes should be merged."""

    remote_branches: Optional[str] = None
    for sha1 in _run_git(['rev-list', '--max-count=5', branch]).split('\n'):
        if remote_branches := _run_git(
                ['branch', '-r', '--contains', sha1, '--list', f'{_REMOTE_REPO}/*']):
            break
    if not remote_branches:
        return None
    if any(rb.endswith(f'/{default}') for rb in remote_branches.split('\n')):
        return None
    return remote_branches.split('\n')[0].rsplit('/', 1)[-1]


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

    def request_review(self, message: str, refs: _References, reviewers: List[str]) -> None:
        """Ask for a review on the specific platform."""

        raise NotImplementedError('This should never happen')

    def get_available_reviewers(self) -> List[str]:
        """List the possible values for reviewers."""

        raise NotImplementedError('This should never happen')

    def _get_review_number(self, branch: str) -> Optional[str]:
        raise NotImplementedError('This should never happen')

    def get_review_url_for(self, branch: Optional[str]) -> str:
        """Give the URL where one can review the code on the given branch."""

        number = None if not branch else self._get_review_number(branch)
        if not number:
            raise _ScriptError('No opened review for branch "%s".', branch)
        return f'https://reviewable.io/reviews/{self.project_name}/{number}'


class _GitlabPlatform(_RemoteGitPlatform):

    def __init__(self, project_name: str) -> None:
        super().__init__(project_name)
        if not gitlab:
            raise _ScriptError(
                'gitlab tool is not installed, please install it:\n'
                '  https://github.com/bayesimpact/bayes-developer-setup/blob/HEAD/gitlab-cli.md')
        self.client = gitlab.Gitlab.from_config()
        self.project = self.client.projects.get(project_name)

    def _get_reviewers(self, reviewers: List[str]) -> List[int]:
        return [user.id for r in reviewers for user in self.client.users.list(username=r)]

    def _get_review_number(self, branch: str) -> Optional[str]:
        raise NotImplementedError('Cannot get Merge Request number from Gitlab yet.')

    def request_review(self, message: str, refs: _References, reviewers: List[str]) -> None:
        title, description = message.split('\n', 1)
        mr_parameters: _GitlabMRRequest = {
            'description': description,
            'source_branch': refs.remote,
            'target_branch': refs.base,
            'title': title,
        }
        # TODO(cyrille): Allow several reviewers
        if users := self._get_reviewers(reviewers):
            mr_parameters['assignee_ids'] = users
        self.project.merge_request.create(mr_parameters)

    def get_available_reviewers(self) -> List[str]:
        return [member.username for member in self.project.members.list()]


class _GithubPlatform(_RemoteGitPlatform):

    def __init__(self, project_name: str) -> None:
        super().__init__(project_name)
        try:
            subprocess.check_output(['hub', 'browse', '-u'])
        except subprocess.CalledProcessError as error:
            raise _ScriptError(
                'hub tool is not installed, or wrongly configured.\n'
                'Please install it with ~/.bayes-developer-setup/install.sh') from error

    def request_review(self, message: str, refs: _References, reviewers: List[str]) -> None:
        """Ask for review on Github."""

        command = [
            'hub', 'pull-request',
            '-m', message,
            '-h', refs.remote,
            '-b', refs.base]
        if reviewers:
            command.extend(['-a', ','.join(reviewers), '-r', ','.join(reviewers)])
        output = subprocess.check_output(command, text=True)
        logging.info(output.replace('github.com', 'reviewable.io/reviews').replace('pull/', ''))

    def get_available_reviewers(self) -> List[str]:
        assignees = json.loads(subprocess.check_output(
            ['hub', 'api', r'repos/{owner}/{repo}/assignees', '--cache', '600'], text=True))
        return [assignee.get('login', '') for assignee in assignees]

    def _get_review_number(self, branch: str) -> Optional[str]:
        return next((
            number for pr in _run_hub(['pr', 'list', r'--format=%I:%H%n']).split('\n')
            for number, head_ref in [pr.split(':', 1)]
            if head_ref == branch), None)


@functools.lru_cache()
def _get_platform() -> _RemoteGitPlatform:
    """Get the relevant review platform once and for all."""

    return _RemoteGitPlatform.from_url(_run_git(['config', f'remote.{_REMOTE_REPO}.url']))


def _request_review(refs: _References, reviewers: List[str]) -> None:
    """Ask for review on the relevant Git platform."""

    message = _make_pr_message(refs, reviewers)
    _get_platform().request_review(message, refs, reviewers)


# TODO(cyrille): Force to use kwargs, since argparse does not type its output.
def prepare_push_and_request_review(
        username: str, base: Optional[str], reviewers: List[str],
        is_forced: bool, is_submit: bool) -> None:
    """Prepare a local Change List for review."""

    if not username:
        raise _ScriptError(
            'Could not find username, most probably you need to setup an email with:\n'
            '  git config user.email <me@bayesimpact.org>')
    refs = _get_git_branches(username, base)
    merge_base = _run_git(['merge-base', 'HEAD', f'{_REMOTE_REPO}/{refs.base}'])
    if not _has_git_diff(merge_base):
        # TODO(cyrille): Update this behavior (depending on base being main or something else).
        raise _ScriptError('All code on this branch has already been submitted.')
    _push(refs, is_forced)
    if not is_forced:
        _request_review(refs, reviewers)
    if not is_submit:
        return
    local_sha = _run_git(['rev-parse', refs.branch])
    remote_sha = _run_git(['rev-parse', f'{_REMOTE_REPO}/{refs.remote}'])
    if local_sha != remote_sha:
        raise _ScriptError('Local branch is not in the same state as remote branch. Not submitting.')
    _run_git(['submit'], env=dict(os.environ, GIT_SUBMIT_AUTO_MERGE='1'))


def _get_default_username(username: str) -> str:
    return username or _run_git(['config', 'user.email']).split('@')[0]


def _browse_to(branch: str) -> None:
    real_branch = _get_existing_remote() or _get_head() if branch == _BROWSE_CURRENT else branch
    url = _get_platform().get_review_url_for(real_branch or branch)
    open_command = 'open' if platform.system() == 'Darwin' else 'xdg-open'
    subprocess.check_output([open_command, url])


def main(string_args: Optional[List[str]] = None) -> None:
    """Parse CLI arguments and run the script."""

    # TODO(cyrille): Auto-complete.
    parser = argparse.ArgumentParser(description='Start a review for your change list.')
    # TODO(cyrille): Allow several reviewer arguments.
    parser.add_argument(
        'reviewers',
        help='Github handles of the reviewers you want to assign to your review, '
        'as a comma separated list.', nargs='*',
    ).completer = lambda **kw: _get_platform().get_available_reviewers()
    parser.add_argument('-f', '--force', action='store_true', help='''
        Forces the push, overwriting any pre-existing remote branch with the prefixed name.
        Also doesn't create the pull/merge request.''')
    parser.add_argument('-s', '--submit', action='store_true', help='''
        Ask GitHub to auto-merge the branch, when all conditions are satisfied.
        Runs 'git submit'.''')
    parser.add_argument('-u', '--username', type=_get_default_username, default='', help='''
        Set the prefix for the remote branch to USER.
        Default is username from the git user's email (such as in username@example.com)''')
    parser.add_argument('-b', '--base', help='''
        Force the pull/merge request to be based on the given base branch on the remote.''')
    # TODO(cyrille): Add completion with pending requests.
    parser.add_argument(
        '--browse', help='''Open the review in a browser window.''',
        nargs='?', const=_BROWSE_CURRENT)
    argcomplete.autocomplete(parser)
    args = parser.parse_args(string_args)
    # TODO(cyrille): Update log level depending on required verbosity.
    logging.basicConfig(level=logging.INFO)
    if args.browse:
        _browse_to(args.browse)
        return
    prepare_push_and_request_review(
        args.username, args.base, args.reviewers, args.force, args.submit)


if __name__ == '__main__':
    try:
        main()
    except _ScriptError as error:
        print(error)
        # TODO(cyrille): Make sure that those are distinct.
        sys.exit(hash(error))
