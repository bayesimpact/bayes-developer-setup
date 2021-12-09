#!/usr/bin/env python3.9
# PYTHON_ARGCOMPLETE_OK
"""Submit a PR after the relevant checks have been done."""

import argparse
import functools
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import typing
from typing import Any, NoReturn, Optional, Sequence, Union

try:
    import argcomplete
except ImportError:
    # This is not needed for the script to work.
    argcomplete = None

# Whether we should print each command before running it (bash xtrace), and the prefix to use.
_XTRACE_PREFIX: list[str] = []
# Whether we should run all hub commands without cache.
_CACHE_BUSTER: list[str] = []
_IFS_REGEX = re.compile(r'[ \n]')
_ONE_DAY = 86400
_TEN_MINUTES = 600
_ONE_MINUTE = 60


def _xtrace(command: Sequence[str], *, prefix_cache: list[str] = _XTRACE_PREFIX) -> None:
    if not prefix_cache:
        return
    sys.stderr.write(
        f'{prefix_cache[0]} ' +
        ' '.join(
            f"'{word}'" if _IFS_REGEX.search(word) else word
            for word in command
        ) + '\n')


def _run(*args: str, silently: bool = False) -> str:
    _xtrace(args)
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as error:
        if not silently:
            logging.error('An error occurred while running:')
            _xtrace(args, prefix_cache=['>'])
            logging.error(error.output.strip())
        raise


def _run_hub(*args: str, cache: Optional[int] = None, silently: bool = False) -> str:
    final_command = ('hub',) + args
    if cache and not _CACHE_BUSTER:
        final_command += ('--cache', str(cache))
    _xtrace(final_command)
    return _run(*final_command, silently=silently)


@functools.cache
def _can_use_hub() -> bool:
    try:
        return bool(shutil.which('hub') and _run_hub('browse', '-u'))
    except subprocess.CalledProcessError:
        return False


def _get_auto_merge_status(env: str) -> Optional[bool]:
    """Whether the script should enable auto-merge.

    True or False if the script should/shouldn't enable. None if it should ask.
    """
    if not _can_use_hub():
        return False
    status = os.getenv(env)
    if not status:
        return None
    return status != '0'


_AUTO_MERGE_ENV_NAME = 'GIT_SUBMIT_AUTO_MERGE'
_GIT_SUBMIT_AUTO_MERGE = _get_auto_merge_status(_AUTO_MERGE_ENV_NAME)
# Disable specific option if user has the experimental NO_GIT_SUBMIT_EXPERIMENTAL env var set.
_SQUASH_ON_GITHUB = not os.getenv('NO_GIT_SUBMIT_EXPERIMENTAL')
_START_BRANCH = _run('git', 'rev-parse', '--abbrev-ref', 'HEAD')
_AUTO_MERGE_REACTION = ':rocket:'
_MUTATION_ENABLE_AUTO_MERGE = '''mutation AutoMerge($pullRequestId: ID!) {
  enablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId, mergeMethod: SQUASH}) {
    pullRequest {autoMergeRequest {enabledAt}}
  }
}'''
_MUTATION_REACT_COMMENT = f'''mutation ReactComment($pullRequestId: ID!, $reaction: String!) {{
  addComment(input: {{body: $reaction, subjectId: $pullRequestId}}) {{
    commentEdge {{
      node {{
        id
      }}
    }}
  }}
}}'''
_MUTATION_DISABLE_AUTO_MERGE = '''mutation CancelAutoMerge($pullRequestId: ID!) {
  disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
    pullRequest {viewerCanEnableAutoMerge}
  }
}'''
_QUERY_GET_PR_COMMENTS = '''query FindComments($pullRequestId: ID!) {
  node(id: $pullRequestId) {
    ... on PullRequest {
      comments(last: 10) {
        nodes {
          id
          body
        }
      }
    }
  }
}'''
_MUTATION_DELETE_COMMENT = '''mutation DeleteComment($commentId: ID!) {
  deleteIssueComment(input: {id: $commentId}) {
    clientMutationId
  }
}'''
_QUERY_GET_PR_INFOS = '''query IsAutoMergeable($headRefName: String!) {
  repository(name: "{repo}", owner: "{owner}") {
    deleteBranchOnMerge
    viewerCanAdminister
    pullRequests(last: 1, headRefName: $headRefName, states: [OPEN]) {
      nodes {
        id
        number
        mergeable
        viewerCanEnableAutoMerge
        viewerCanDisableAutoMerge
        autoMergeRequest {enabledAt}
      }
    }
  }
}'''


def _graphql(query: str, cache: Optional[int] = None, **kwargs: str) -> dict[str, Any]:
    kwargs['query'] = query
    args = [arg for key, value in kwargs.items() for arg in ('-F', f'{key}={value}')]
    return typing.cast(dict[str, Any], json.loads(_run_hub('api', 'graphql', *args, cache=cache)))


# TODO(cyrille): Add timeout/1char possibilities.
def _ask_yes_no(question: str) -> bool:
    if not sys.stdin.isatty():
        print(f'{question} Answering N, since not a TTY.')
        return False
    answer = input(f'{question} [y/N]')
    return answer.lower().startswith('y')


class _Arguments(typing.Protocol):
    abort: bool
    branch: str
    cache: bool
    default: '_Branch'
    force: bool
    prefix: Optional[str]
    rebase: bool
    user: str
    xtrace: Optional[str]


class _AutoMerge(typing.NamedTuple):
    can_disable: bool
    can_enable: bool
    is_enabled: bool


class _PrInfos(typing.NamedTuple):
    auto_merge: _AutoMerge
    node_id: str
    number: int


class _Branch(typing.NamedTuple):
    # The local name for the branch.
    local: str
    # The remote at which the tracked branch is.
    remote: str
    # The sha1 where local is at the start of the script.
    initial: str
    # The name of the remote tracked branch.
    merge: str

    @staticmethod
    def get_sha1(branch: Union[str, '_Branch']) -> str:
        """Returns the sha1 of the given (local) branch."""

        if isinstance(branch, _Branch):
            branch = branch.local
        return _run('git', 'rev-parse', branch)

    @property
    def tracked(self) -> str:
        return f'{self.remote}/{self.merge}'

    def push(self) -> None:
        _run('git', 'push', self.remote, f'{self.local}:{self.merge}')

    def clean(self, *, keep_remote: bool = False) -> None:
        _run('git', 'branch', '-D', self.local)
        if not keep_remote:
            _run('git', 'push', '-d', self.remote, self.merge)

    def with_initial(self, ref: str) -> '_Branch':
        return self._replace(initial=self.get_sha1(ref))

    def reset(self) -> None:
        """Reset the local branch to its initial state."""

        logging.info('\tSet branch %s to %s', self.local, self.initial)
        _run('git', 'branch', '-f', self.local, self.initial)


def _is_git_clean() -> bool:
    try:
        _run('git', 'diff', 'HEAD', '--exit-code', silently=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _get_base_remote() -> str:
    try:
        return _run('git', 'config', 'branch.main.remote', silently=True)
    except subprocess.CalledProcessError:
        try:
            return _run('git', 'config', 'branch.master.remote', silently=True)
        except subprocess.CalledProcessError:
            return 'origin'


def _get_remote_head(base_remote: str) -> str:
    try:
        return _run(
            'git', 'rev-parse', '--abbrev-ref', f'{base_remote}/HEAD', silently=True).split('/')[1]
    except subprocess.CalledProcessError:
        pass
    if _can_use_hub():
        head: str = json.loads(
            _run_hub('api', 'repos/{owner}/{repo}', cache=_ONE_DAY))['default_branch']
    else:
        head = 'main'
    logging.error(
        'No %s/HEAD reference set.\nPlease set it using "git remote set-head origin %s".',
        base_remote, head)
    return head


@functools.cache
def _get_default_branch() -> _Branch:
    base_remote: str = _get_base_remote()
    remote_head: str = _get_remote_head(base_remote)
    full_remote_head = f'{base_remote}/{remote_head}'
    for branch in _run('git', 'for-each-ref', '--format=%(refname:short)', 'refs/heads').split('\n'):
        try:
            remote = _run('git', 'rev-parse', '--abbrev-ref', f'{branch}@{{upstream}}', silently=True)
        except subprocess.CalledProcessError:
            continue
        if remote == full_remote_head:
            local = branch
            break
    else:
        logging.warning(
            '"%s" is not checked out locally. checking it as "%s".', full_remote_head, remote_head)
        _run('git', 'branch', remote_head, '--track', full_remote_head)
        local = remote_head
    initial = _Branch.get_sha1(local)
    return _Branch(local=local, remote=base_remote, merge=remote_head, initial=initial)


def _get_local_branches(default_branch: str) -> list[str]:
    """List branches in user-preferred order.

    The default branch is excluded.
    """

    all_branches = _run('git', 'branch', '--format=%(refname:short)').split('\n')
    all_branches.remove(default_branch)
    return all_branches


def _get_remote_prefixed_branches(remote_prefix: str) -> list[str]:
    return [
        branch.removeprefix(remote_prefix)
        for branch in _run(
            'git', 'branch', '-r', '--format=%(refname:short)',
            '--list', f'{remote_prefix}*',
        ).split('\n')]


def _show_available_branches(default_branch: str, remote_prefix: Optional[str] = None) -> None:
    local_branches = _get_local_branches(default_branch)
    logging.info('local branches:\n%s', '\n'.join(local_branches))
    if not remote_prefix:
        return
    logging.info(
        'remote dangling branches:\n%s', '\n'.join(_get_remote_prefixed_branches(remote_prefix)))


def _get_branch(branch: str, default: _Branch, prefix: Optional[str]) -> _Branch:
    # Ensures that current dir is clean.
    _check_clean_state(branch, default.local, prefix)
    try:
        remote = _run('git', 'config', f'branch.{branch}.remote', silently=True)
    except subprocess.CalledProcessError:
        if prefix:
            _run('git', 'fetch')
            _run('git', 'branch', branch, '-t', f'{prefix}{branch}')
            remote = default.remote
        else:
            remote = ''
    merge = remote and _run('git', 'config', f'branch.{branch}.merge').removeprefix('refs/heads/')
    initial = _Branch.get_sha1(branch)
    return _Branch(local=branch, remote=remote, merge=merge, initial=initial)


def enable_auto_merge(pr_node_id: str) -> bool:
    """Ask Github to merge this PR once CI is successful."""

    mutation_answer = _graphql(_MUTATION_ENABLE_AUTO_MERGE, pullRequestId=pr_node_id)
    if not mutation_answer['data']['enablePullRequestAutoMerge']['pullRequest']['autoMergeRequest'][
            'enabledAt']:
        return False
    mutation_answer = _graphql(
        _MUTATION_REACT_COMMENT, pullRequestId=pr_node_id, reaction=_AUTO_MERGE_REACTION)
    return bool(mutation_answer['data']['addComment']['commentEdge']['node']['id'])


def disable_auto_merge(pr_node_id: str) -> bool:
    """Cancel auto-merge request."""

    mutation_answer = _graphql(_MUTATION_DISABLE_AUTO_MERGE, pullRequestId=pr_node_id)
    if not mutation_answer['data']['disablePullRequestAutoMerge']['pullRequest'][
            'viewerCanEnableAutoMerge']:
        return False
    all_comments = _graphql(_QUERY_GET_PR_COMMENTS, pullRequestId=pr_node_id, cache=_ONE_MINUTE)
    for comment in all_comments['data']['node']['comments']['nodes']:
        if comment['body'] != _AUTO_MERGE_REACTION:
            continue
        try:
            _graphql(_MUTATION_DELETE_COMMENT, commentId=comment['id'])
        except subprocess.CalledProcessError:
            pass
    return True


def get_pr_info(branch: str, should_auto_merge: bool = bool(_GIT_SUBMIT_AUTO_MERGE)) \
        -> Optional[_PrInfos]:
    """Fetch relevant info for branch."""

    if not _can_use_hub():
        return None
    repo_infos = _graphql(_QUERY_GET_PR_INFOS, headRefName=branch)['data']['repository']
    raw_pr_infos = repo_infos['pullRequests']['nodes'][0]
    can_auto_merge = raw_pr_infos['mergeable'] == 'MERGEABLE' or \
        raw_pr_infos['viewerCanEnableAutoMerge'] or \
        raw_pr_infos['viewerCanDisableAutoMerge']
    will_auto_merge = bool((raw_pr_infos['autoMergeRequest'] or {}).get('enabledAt'))
    pr_infos = _PrInfos(_AutoMerge(
        is_enabled=will_auto_merge,
        can_enable=raw_pr_infos['viewerCanEnableAutoMerge'],
        can_disable=raw_pr_infos['viewerCanDisableAutoMerge'],
    ), node_id=raw_pr_infos['id'], number=raw_pr_infos['number'])
    may_auto_merge = can_auto_merge or will_auto_merge
    if repo_infos['deleteBranchOnMerge'] or not may_auto_merge:
        return pr_infos
    logging.warning("The remote branch won't be deleted after auto-merge.")
    if _ask_yes_no('Do you want to update your repository settings?'):
        _run_hub(
            'api', 'repos/{owner}/{repo}', '-X', 'PATCH', '-f', 'delete_branch_on_merge=true')
    else:
        logging.info(
            'You can still do it from this page:\n\t%s',
            _run_hub('browse', '-u', '--', 'settings#merge_types_delete_branch'))
    if should_auto_merge and not can_auto_merge:
        logging.warning('The repository is not set to enable auto-merge.')
        if repo_infos['viewerCanAdminister']:
            logging.info(
                'You can do it from this page:\n\t%s',
                _run_hub('browse', '-u', '--', 'settings#merge_types_auto_merge'))
        else:
            logging.info('You can contact a repo admin to set it up for you.')
    return pr_infos


def _check_clean_state(branch: str, default_branch: str, remote_prefix: Optional[str]) -> None:
    if branch == default_branch:
        logging.error('A branch is required:')
        _show_available_branches(default_branch, remote_prefix)
        sys.exit(1)
    if not _is_git_clean():
        logging.error(
            'Current git status is dirty. Commit, stash or revert your changes before submitting.')
        sys.exit(2)
    if remote_prefix:
        return
    try:
        _run('git', 'rev-parse', '--verify', branch, silently=True)
    except subprocess.CalledProcessError:
        logging.error('%s is not a valid branch', branch)
        _show_available_branches(default_branch)
        sys.exit(8)


def _should_auto_merge(branch: str, should_force: bool, pr_infos: Optional[_PrInfos]) -> bool:
    """Ensure that the Continuous Integration is successful."""

    if not pr_infos:
        return False
    try:
        _run_hub('ci-status', branch, silently=True)
        return False
    except subprocess.CalledProcessError as error:
        ci_status = error.output.strip()
    if should_force:
        logging.warning('forcing submission despite CI status "%s".', ci_status)
        return bool(_GIT_SUBMIT_AUTO_MERGE)
    logging.info('CI status is "%s"', ci_status)
    should_auto_merge = _GIT_SUBMIT_AUTO_MERGE
    if pr_infos.auto_merge.is_enabled:
        logging.info('Auto-merge is already enabled for this PR.')
        return False
    if not pr_infos.auto_merge.can_enable:
        should_auto_merge = False
    if should_auto_merge is None:
        should_auto_merge = _ask_yes_no('Do you want to enable auto-merge?')
        logging.info(
            'You can avoid this question by setting %s to 0 or 1 in your environment.',
            _AUTO_MERGE_ENV_NAME)
    if not should_auto_merge:
        logging.info('Use "-f" if you want to force submission.')
        _run_hub('ci-status', '-v', branch)
    return should_auto_merge


def abort_submit(branch: str, pr_infos: Optional[_PrInfos]) -> None:
    """Checkout the given branch and disable auto-merge.

    It assumes the branch already exists.
    """
    _run('git', 'checkout', branch)
    if not pr_infos:
        logging.warning("Unable to cancel auto-merge (you're not using hub for this project).")
        return
    if not pr_infos.auto_merge.is_enabled:
        logging.info('Auto-merge is not enabled for this pull-request yet. Nothing to abort.')
        return
    if pr_infos.auto_merge.can_disable:
        try:
            disable_auto_merge(pr_infos.node_id)
            logging.info('Auto-merge for "%s" has been cancelled.', branch)
            return
        except subprocess.CalledProcessError:
            logging.error('Something wrong happened while cancelling auto-merge.')
            raise
    logging.warning("You don't have the rights to cancel this pull-request.")
    logging.info('Please contact the project admin.')


def abort(*branches: _Branch) -> NoReturn:
    """Reset all the given branches, and fail."""

    logging.error('Something went wrong, aborting:')
    for branch in branches:
        branch.reset()
    if _START_BRANCH != _run('git', 'rev-parse', 'abbrev-ref', 'HEAD'):
        logging.info('\tGoing back to branch %s', _START_BRANCH)
        _run('git', 'checkout', '-f', _START_BRANCH)
    sys.exit(7)


def _is_ancestor(ref1: str, ref2: str) -> bool:
    try:
        _run('git', 'merge-base', '--is-ancestor', ref1, ref2, silently=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _rebase(
        onto: str, branch: str, *, interactive: bool = False,
        should_abort_on_conflict: bool = True) -> None:
    cmd = ('git', 'rebase', onto, branch) + (('-i',) if interactive else ())
    try:
        _run(*cmd)
        return
    except subprocess.CalledProcessError:
        if should_abort_on_conflict:
            _run('git', 'rebase', '--abort')
        else:
            logging.warning('Please resolve conflicts and run `git rebase --continue`.')
        raise


def _handle_rebase(default: _Branch, branch: _Branch, force: bool = False) -> None:
    """Check that the changes are bundled as one commit on top of origin/default_branch."""

    abort_on_conflict = not force
    force = force or not _SQUASH_ON_GITHUB
    logging.debug('Rebasing "%s" onto "%s"', branch.local, default.initial)
    penultimate = _Branch.get_sha1(f'{branch.local}^')
    while default.initial != penultimate:
        if default.initial == _Branch.get_sha1(branch):
            logging.error('No changes to submit')
            sys.exit(3)
        if _is_ancestor(penultimate, default.initial):
            if force:
                _rebase(default.tracked, branch.local, should_abort_on_conflict=abort_on_conflict)
            break
        logging.warning(
            'You should first group all your changes in one commit:\n\tgit rebase -i "%s" "%s"',
            default.tracked, branch.local)
        if not force:
            sys.exit(12)
        if not _ask_yes_no('Rebase now?'):
            sys.exit(4)
        _rebase(
            default.tracked, branch.local, interactive=True,
            should_abort_on_conflict=abort_on_conflict)
        penultimate = _Branch.get_sha1(f'{branch.local}^')


def _push_to_remote(*, branch: _Branch, default: Optional[_Branch] = None, silently: bool = False) \
        -> None:
    if default:
        msg = 'is not tracked and has probably never been reviewed.'
        cmd = ('git', 'push', '-u', default.remote, branch.local)
    else:
        msg = 'is not up-to-date with its upstream.'
        cmd = ('git', 'push', '-f', branch.remote, f'{branch.local}:{branch.merge}')
    logging.warning('The branch %s %s\n\t%s', branch.local, msg, ' '.join(cmd))
    if silently or _ask_yes_no('Push now?'):
        try:
            _run(*cmd)
        except subprocess.CalledProcessError:
            branches = (branch, default) if default else (branch,)
            abort(*branches)
    if not silently:
        sys.exit(5)


def _merge_now_or_later(pr_infos: _PrInfos, should_auto_merge: bool, sha1: str) -> bool:
    """Ask for a merge through github's API.

    Return True if the merge is completed, False if it will be later on.
    """

    if pr_infos.auto_merge.is_enabled:
        logging.info('GitHub will auto-merge this pull-request once CI is successful.')
        return False
    if not should_auto_merge:
        logging.info('Merging on GitHub.')
        _run_hub(
            'api', '-X', 'PUT', f'/repos/{{owner}}/{{repo}}/pulls/{pr_infos.number}/merge',
            '-F', 'merge_method=squash', '-F', f'sha={sha1}')
        return True
    enable_auto_merge(pr_infos.node_id)
    logging.info('Your branch will be merged once CI is successful.')
    return False


def _prepare_args(args: _Arguments) -> _Arguments:
    args.abort = args.abort or args.rebase
    if args.abort and not args.user:
        args.user = _run('git', 'config', 'user.email').split('@', 1)[0]
    if not args.branch:
        args.branch = _START_BRANCH
    if not args.cache:
        del _CACHE_BUSTER[:]
        _CACHE_BUSTER.append('busted')
    args.default = _get_default_branch()
    args.prefix = f'{args.default.remote}/{args.user}-' if args.abort else None
    return args


def _branch_completer(*, parsed_args: _Arguments, **unused_kwargs: Any) -> list[str]:
    args = _prepare_args(parsed_args)
    local_branches = _get_local_branches(args.default.local)
    if not args.prefix:
        return local_branches
    return local_branches + _get_remote_prefixed_branches(args.prefix)


def _user_completer(*, prefix: str, parsed_args: _Arguments, **unused_kwargs: Any) -> set[str]:
    args = _prepare_args(parsed_args)
    remote_prefix = f'{args.default.remote}/'
    return {
        name.removeprefix(remote_prefix).split('-', 1)[0]
        for name in _run(
            'git', 'branch', '-r', '--format=%(refname:short)',
            '--list', f'{remote_prefix}{prefix}*').split('\n')
        if '-' in name}


def main() -> None:
    """Parse arguments, and do whatever needs to be done."""

    parser = argparse.ArgumentParser('Submit the given or current branch.')
    branch_action = parser.add_argument(
        'branch', default='', help='''The branch to submit.''', nargs='?')
    parser.add_argument('--xtrace', '-x', help='''Debug.''')
    parser.add_argument('--force', '-f', action='store_true', help='''
        Forces the submit, regardless of the CI status.''')
    parser.add_argument('--abort', '--abort-auto-submit', '-a', action='store_true', help='''
        Cancel any auto-submission.
        Also recreate a branch from origin, without its username prefix.''')
    parser.add_argument('--rebase', '-r', action='store_true', help='''
        Rebase the given branch on top of origin/HEAD and try to submit it.''')
    user_action = parser.add_argument('--user', '-u', default='', help='''
        Set the prefix for the remote branch to USER. Default is username from the git user's email
        (such as in username@example.com). Only useful for '--abort'/'--rebase'.''')
    parser.add_argument('--no-cache', dest='cache', action='store_false', help='''
        Clear the cache mechanism on hub API calls.''')
    if argcomplete:
        setattr(branch_action, 'completer', _branch_completer)
        setattr(user_action, 'completer', _user_completer)
        argcomplete.autocomplete(parser)
    args = _prepare_args(parser.parse_args())
    if args.xtrace:
        del _XTRACE_PREFIX[:]
        _XTRACE_PREFIX.append(args.xtrace)
    branch = _get_branch(args.branch, args.default, args.prefix)
    pr_infos = get_pr_info(branch.merge)
    if args.abort:
        abort_submit(args.branch, pr_infos)
        if not args.rebase:
            return
    _run('git', 'fetch')
    default = args.default.with_initial(args.default.tracked)
    _handle_rebase(default, branch, force=args.rebase)
    logging.info('Branch "%s" has been rebased onto "%s"', branch, default.initial)
    pr_infos = get_pr_info(branch.merge)
    if not branch.remote:
        _push_to_remote(branch=branch, default=default)
    if args.rebase or _Branch.get_sha1(branch) != _Branch.get_sha1(branch.tracked):
        _push_to_remote(branch=branch, silently=True)
    if not _SQUASH_ON_GITHUB or not pr_infos:
        _run('git', 'checkout', default.local)
        try:
            _rebase(branch.local, default.local)
            default.push()
        except subprocess.CalledProcessError:
            abort(default, branch)
        branch.clean()
        return
    should_auto_merge = _should_auto_merge(args.branch, args.force, pr_infos)
    try:
        keep_remote = not _merge_now_or_later(pr_infos, should_auto_merge, branch.initial)
    except subprocess.CalledProcessError:
        abort(default, branch)
    _run('git', 'checkout', default.local)
    _run('git', 'pull', '--ff-only')
    branch.clean(keep_remote=keep_remote)


if __name__ == '__main__':
    main()
