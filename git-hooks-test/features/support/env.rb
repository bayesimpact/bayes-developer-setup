require 'aruba/cucumber'

Before do
  set_environment_variable 'GIT_AUTHOR_NAME', 'testing-author'
  set_environment_variable 'GIT_COMMITTER_NAME', 'testing-author'
  set_environment_variable 'GIT_AUTHOR_EMAIL', 'testing-author@example.com'
  set_environment_variable 'GIT_COMMITTER_EMAIL', 'testing-author@example.com'
end

World Module.new {
  def git_hash(name, dir='.')
    sha1 = ''
    cd (dir) {
      sha1 = `git rev-parse --quiet --verify "#{name}"`.chomp
    }
    return sha1
  end
}
