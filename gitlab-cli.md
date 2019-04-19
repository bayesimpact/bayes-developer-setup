# GitLab CLI

## Installation

Run:

```sh
sudo pip install python-gitlab
```

## Configuration

This is the configuration to access the main GitLab server (gitlab.com).

1. Go to your [GitLab account](https://gitlab.com/profile/personal_access_tokens) and create a
   personal access token with API access. You will use it below instead of `MY_TOKEN`.

2. Create a file in `~/.python-gitlab.cfg` with the following content:

```ini
[global]
default = main
ssl_verify = true

[main]
url = https://gitlab.com
private_token = MY_TOKEN
```
