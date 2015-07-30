#!/usr/bin/python

import os

home = os.getenv('HOME')

if os.path.exists(home + '/.gitconfig'):
  print '~/.gitconfig exists. Skipping.'
  print 'Delete it and rerun if you wish to replace it.'
else:
  print 'Creating ~/.gitconfig'
  os.system('cp gitconfig %s/.gitconfig' % home)

if os.path.exists(home + '/.git_template'):
  print '~/.git_template exists. Skipping.'
  print 'Delete it and rerun if you wish to replace it.'
else:
  print 'Creating ~/.git_template'
  os.system('cp -R git_template %s/.git_template' % home)
