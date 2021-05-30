#!/usr/bin/env python3
"""
Pushes the current branch to the remote repository,
naming the remote branch with a user-specific prefix,
and creates a pull/merge request (depending whether on GitHub or GitLab)
with the specified reviewers (if any).

PYTHON_ARGCOMPLETE_OK
"""

import argparse
import logging
import os
import subprocess
import typing
from typing import Any, List, Optional

try:
    import argcomplete
except ImportError:
    # This is not necessary if you don't want auto-completion.
    argcomplete = None
try:
    import gitlab
except ImportError:
    # This is not needed when pushing to a Github repo.
    gitlab = None
import unidecode


def _run_git(command: List[str], **kwargs: Any) -> List[str]:
    return subprocess.check_output(['git'] + command, text=True, **kwargs).strip()


_REMOTE_REPO = 'origin'
_DEFAULT_USERNAME = _run_git(['config', 'user.email']).split('@')[0]


def _has_git_diff(base: str) -> bool:
    return bool(subprocess.run(['git', 'diff', '--quiet', base]).returncode)


class References(typing.NamedTuple):
    """Simple structure containing all needed branch references."""

    default: str
    branch: str
    base: str
    remote_base: str
    remote: str


def _get_git_branches(username: str, base: Optional[str]) -> References:
    branch = _run_git(['rev-parse', '--abbrev-ref', 'HEAD'])
    if not branch:
        raise ValueError('Empty branch "%s"' % branch)
    default = _run_git(['rev-parse', '--abbrev-ref', f'{_REMOTE_REPO}/HEAD']).split('/')[1]
    if branch == default:
        # TODO(cyrille): List available branches.
        raise ValueError('branch required\n')
    if _has_git_diff('HEAD'):
        raise ValueError(
            'Current git status is dirty. '
            'Commit, stash or revert your changes before sending for review.')

    if not base:
        base = _get_best_base_branch(branch, default) or default
    remote_base = f'{_REMOTE_REPO}/{base}'

    try:
        remote_branch = _run_git(['config', f'branch.{branch}.merge'])[len('refs.heads.'):]
    except subprocess.CalledProcessError:
        remote_branch = _cleanup_branch_name(f'{username}-{branch}')

    return References(default, branch, base, remote_base, remote_branch)


def _get_best_base_branch(branch: str, default: str) -> Optional[str]:
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
    return unidecode.unidecode(''.join(branch.split('#')))


def _push(refs, is_forced: bool) -> None:
    command = ['push']
    if is_forced:
        command.append('-f')
    command.extend(['-u', _REMOTE_REPO, f'{refs.branch}:{refs.remote}'])
    _run_git(command)


def _make_pr_message(refs: References, reviewers: Optional[str]) -> str:
    return _run_git(['log', '--format=%B', f'{refs.base}..{refs.branch}']) + \
        _run_git_review_hook(refs.branch, refs.remote, reviewers)


def _run_git_review_hook(branch: str, remote_branch: str, reviewer: Optional[str]) -> str:
    hook_script = f'{_run_git(["rev-parse", "--show-toplevel"])}/.git-review-hook'
    if not os.access(hook_script, os.X_OK):
        return ''
    return subprocess.check_output(hook_script, text=True, env=dict(os.environ, **{
        'BRANCH': branch,
        'REMOTE_BRANCH': remote_branch,
        'REVIEWER': reviewer or '',
    }))


def _request_review(refs: References, reviewers: Optional[str]) -> None:
    remote_url = _run_git(['config', f'remote.{_REMOTE_REPO}.url'])
    message = _make_pr_message(refs, reviewers)
    if 'gitlab.com' in remote_url:
        _request_mr(remote_url, message, refs, reviewers)
        return
    if 'github.com' in remote_url:
        _request_pr(message, refs, reviewers)
        return
    raise NotImplementedError('Review requests are available only for Gitlab and Github.')


def _request_mr(remote_url: str, message: str, refs: References, reviewers: Optional[str]) -> None:
    if not gitlab:
        raise ValueError(
            'gitlab tool is not installed, please install it:\n'
            # TODO(cyrille): Switch to main, once this repo has switched.
            '  https://github.com/bayesimpact/bayes-developer-setup/blob/master/gitlab-cli.md')
    client = gitlab.Gitlab.from_config()
    project_name = remote_url[len('git@gitlab.com:'):-len('.git')]
    project = client.projects.get(project_name)

    title, description = message.split('\n', 1)
    mr_parameters = {
        'description': description,
        'source_branch': refs.remote,
        'target_branch': refs.base,
        'title': title,
    }
    # TODO(cyrille): Allow several reviewers
    if reviewers and (users := client.users.list(username=reviewers)):
        mr_parameters['assignee_id'] = users[0].id
    project.merge_request.create(mr_parameters)


def _request_pr(message: str, refs: References, reviewers: Optional[str]) -> None:
    command = [
        'hub', 'pull-request',
        '-m', message,
        '-h', refs.remote,
        '-b', refs.base]
    if reviewers:
        command.extend(['-a', reviewers, '-r', reviewers])
    output = subprocess.check_output(command, text=True)
    logging.info(output.replace('github.com', 'reviewable.io/reviews').replace('pull/', ''))


def prepare_push_and_request_review(
        username: str, base: Optional[str], reviewers: Optional[str],
        is_forced: bool, is_submit: bool) -> None:
    """Prepare a local Change List for review."""

    if not username:
        raise ValueError(
            'Could not find username, most probably you need to setup an email with:\n'
            '  git config user.email <me@bayesimpact.org>')
    refs = _get_git_branches(username, base)
    merge_base = _run_git(['merge-base', 'HEAD', refs.remote_base])
    if not _has_git_diff(merge_base):
        raise ValueError('All code on this branch has already been submitted')
    _push(refs, is_forced)
    if not is_forced:
        _request_review(refs, reviewers)
    if not is_submit:
        return
    local_sha = _run_git(['rev-parse', refs.branch])
    remote_sha = _run_git(['rev-parse', f'{_REMOTE_REPO}/{refs.remote}'])
    if local_sha != remote_sha:
        raise ValueError('Local branch is not in the same state as remote branch. Not submitting.')
    _run_git(['submit'], env=dict(os.environ, GIT_SUBMIT_AUTO_MERGE='1'))


def main(string_args: Optional[List[str]] = None) -> None:
    """Parse CLI arguments and run the script."""

    # TODO(cyrille): Auto-complete.
    parser = argparse.ArgumentParser(description='Start a review for your change list.')
    # TODO(cyrille): Allow several reviewer arguments.
    parser.add_argument(
        'reviewers',
        help='Github handles of the reviewers you want to assign to your review, '
        'as a comma separated list.', nargs='?')
    parser.add_argument('-f', '--force', action='store_true', help='''
        Forces the push, overwriting any pre-existing remote branch with the prefixed name.
        Also doesn't create the pull/merge request.''')
    parser.add_argument('-s', '--submit', action='store_true', help='''
        Ask GitHub to auto-merge the branch, when all conditions are satisfied.
        Runs 'git submit'.''')
    parser.add_argument('-u', '--username', default=_DEFAULT_USERNAME, help='''
        Set the prefix for the remote branch to USER.
        Default is username from the git user's email (such as in username@example.com)''')
    parser.add_argument('-b', '--base', help='''
        Force the pull/merge request to be based on the given base branch on the remote.''')
    argcomplete.autocomplete(parser)
    args = parser.parse_args(string_args)
    # TODO(cyrille): Update log level depending on required verbosity.
    logging.basicConfig(level=logging.INFO)
    prepare_push_and_request_review(
        args.username, args.base, args.reviewers, args.force, args.submit)


if __name__ == '__main__':
    main()
