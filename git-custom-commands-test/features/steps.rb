Given(/^a dummy git repo in "([^"]+)"$/) do |dir_name|
  step %(a directory named "#{dir_name}")
  cd(dir_name) {
    step %(I successfully run `git init --quiet`)
    step %(I commit a file "dummy" with:), %(dummy content)
    # Hop in detached mode so that the branches can be updated.
    step %(I successfully run `git checkout --detach --quiet`)
  }
end

Given(/^a dummy git repo in "([^"]+)" whose default branch is "([^"]+)"$/) do |dir_name, branch|
  step %(a directory named "#{dir_name}")
  cd(dir_name) {
    step %(I successfully run `git init --quiet`)
    step %(I commit a file "dummy" with:), %(dummy content)
    # Hop in detached mode so that the branches can be updated.
    step %(I successfully run `git checkout #{branch}`)
  }
end

Given(/^I am in a "([^"]+)" git repo cloned from "([^"]+)"$/) do |dir_name, cloned_dir|
  step %(I successfully run `git clone "#{cloned_dir}/.git" "#{dir_name}" --quiet`)
  step %(I cd to "#{dir_name}")
end

Given(/^I create a "([^"]+)" git branch from "([^"]+)"$/) do |branch_name, origin_branch|
  step %(I successfully run `git checkout -b "#{branch_name}" "#{origin_branch}"`)
end

Given(/^I commit a file "([^"]+)" with:$/) do |file_name, content|
  step %(a file named "#{file_name}" with:), content
  step %(I successfully run `git add "#{file_name}"`)
  step %(I successfully run `git commit -m "No message"`)
end

Given(/^a file "([^"]+)" is committed on "([^"]+)" git branch in "([^"]+)" with:$/) do |file_name, branch, repo, content|
  cd("../#{repo}") {
    sha1 = git_hash('HEAD', '.')
    step %(I successfully run `git checkout #{branch} --quiet`)
    step %(I commit a file "#{file_name}" with:), content
    step %(I successfully run `git checkout --detach #{sha1} --quiet`)
  }
end

Given(/^I should be on "([^"]+)" git branch$/) do |name|
  cd('.') {
    branch = `git rev-parse --abbrev-ref HEAD`.chomp
    expect(branch).to eql(name)
  }
end

Given(/^the "([^"]+)" git branch (?:in "([^"]+)" )?should(?: still)?( not)? exist$/) do |name, repo, not_exist|
  dir = '.'
  if repo
    dir = "../#{repo}"
  end
  sha1 = git_hash(name, dir)
  if not_exist
    expect(sha1).to be_empty
  else
    expect(sha1).not_to be_empty
  end
end

Given(/^the "([^"]+)" git branch should be in sync with "([^"]+)" in "([^"]+)"$/) do |name, other_branch, repo|
  dir = '.'
  if repo
    dir = "../#{repo}"
  end
  sha1 = git_hash(name)
  other_sha1 = git_hash(other_branch, dir)
  expect(sha1).to eql(other_sha1)
end

Given(/^I switch "([^"]+)" to "([^"]+)" branch$/) do |dir_name, branch|
  cd(dir_name) {
    step %(I successfully run `git branch -m "#{branch}"`)
  }
end
