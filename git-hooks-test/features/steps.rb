Given(/^I use the defined hooks$/) do
  step %(I successfully run `git config --global core.hooksPath /usr/share/hooks`)
end

Given(/^I use the defined hook "([^"]+)"$/) do |hook_name|
  step %(I successfully run `mkdir -p /tmp/hook-#{hook_name}`)
  step %(I successfully run `cp /usr/share/hooks/#{hook_name} /tmp/hook-#{hook_name}/`)
  step %(I successfully run `git config --global core.hooksPath /tmp/hook-#{hook_name}`)
end

Given(/^I am in a dummy git repo in "([^"]+)"$/) do |dir_name|
  step %(a directory named "#{dir_name}")
  step %(I cd to "#{dir_name}")
  step %(I successfully run `git init --quiet`)
  step %(I force commit a file "dummy" with message:), %(No message)
  step %(I run `git branch -m main`)
end

Given (/^I (force )?commit everything$/) do |force|
  step %(I run `git add -A`)
  step %(I successfully run `git commit -#{force ? 'n' : ''}m "dummy content"`)
end

Given(/^I (force )?commit a file "([^"]+)" with message:$/) do |force, file_name, content|
  step %(a file named "#{file_name}" with:), %(dummy content)
  step %(I run `git add "#{file_name}"`)
  step %(I #{force ? 'successfully ' : ''}run `git commit -#{force ? 'n' : ''}m "#{content}"`)
end

Given(/^I am in a Bazel repo$/) do
  step %(an empty file named "WORKSPACE")
  step %(an empty file named "BUILD")
  step %(I force commit everything)
end

Given(/^I am in a "([^"]+)" git repo cloned from "([^"]+)"$/) do |dir_name, cloned_dir|
  step %(I successfully run `git clone "#{cloned_dir}/.git" "#{dir_name}" --quiet`)
  step %(I cd to "#{dir_name}")
end

Given(/^I create a "([^"]+)" git branch from "([^"]+)"$/) do |branch_name, origin_branch|
  step %(I successfully run `git checkout -b "#{branch_name}" "#{origin_branch}"`)
end

Given(/^I should be on "([^"]+)" git branch$/) do |name|
  cd('.') {
    branch = `git rev-parse --abbrev-ref HEAD`.chomp
    expect(branch).to eql(name)
  }
end

# TODO(cyrille): Make sure we check untracked files.
Given(/^the git status should be clean$/) do
  cd('.') {
    diff = `git diff HEAD --shortstat 2> /dev/null | tail -n1`.chomp
    expect(diff).to eql('')
  }
end


