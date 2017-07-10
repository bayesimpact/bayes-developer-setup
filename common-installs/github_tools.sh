#!/usr/bin/env bash
#
# A script to install git add-ons.

readonly SHELLRC="${HOME}/.${SHELL#/bin/}rc"

# Check if complete tools have already been installed for git.
# if echo $(complete | grep " git$"); then
#   echo 'Looks like completion tools are arleady installed for git!'
#   exit
# fi

# Propose useful Github addons.
read -p "Would you like to add git-completion and git-prompt, two useful git tools? " -n 1 -r
echo # Add a blank line.
if [[ $REPLY =~ ^[Yy]$ ]]; then
  curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash > ${HOME}/.git-completion.sh
  curl https://raw.githubusercontent.com/git/git/master/contrib/completion/git-prompt.sh > ${HOME}/.git-prompt.sh
  echo '# Git tools.' >> $SHELLRC
  echo 'source ~/.git-completion.sh' >> $SHELLRC
  echo 'source ~/.git-prompt.sh' >> $SHELLRC
  echo "Add the following line to your bash profile."
  echo export PS1='\[\033[0;94m\]\W $(__git_ps1 " (%s)")$ \[\033[0m\]'
  echo export PS1='\[\033[0;94m\]\W $(__git_ps1 " (%s)")$ \[\033[0m\]' >> $SHELLRC # Issue sourcing after export. Needs another layer of quotes.
  source $SHELLRC
fi
