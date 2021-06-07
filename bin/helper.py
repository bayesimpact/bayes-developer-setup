"""Helper functions for git command scripts.
TODO(cyrille): Use those in a git-submit python script.
"""

import functools
import subprocess
from typing import Any, List

# TODO(cyrille): Get it from git config.
# Name of the remote to which the script pushes.
REMOTE_REPO = 'origin'


def run_git(command: List[str], **kwargs: Any) -> str:
    """Run git and return its output without trailing newline."""

    return subprocess.check_output(['git'] + command, text=True, **kwargs).strip()


class ScriptError(ValueError):
    """Errors specific to our scripts."""

    def __init__(self, msg: str, *args: Any) -> None:
        super().__init__(msg % args if args else msg)
        self._stable_message = msg

    def __hash__(self) -> int:
        return sum((ord(char) - 64) * 53 ** i for i, char in enumerate(self._stable_message))


@functools.lru_cache()
def get_default() -> str:
    """Return the default remote branch for the repo."""

    try:
        return run_git(['rev-parse', '--abbrev-ref', f'{REMOTE_REPO}/HEAD']).split('/')[1]
    except subprocess.CalledProcessError as error:
        raise ScriptError(
            'Unable to find a remote HEAD reference.\n'
            f'Please run `git remote set-head {REMOTE_REPO} -a` and rerun your command.'
        ) from error
