#!/bin/bash

# (Re)start Flask app and test sending a payload against the endpoint that receives Github
# notifications.
# Usage:
# ./test-flask-endpoint issue_comment github_notification_issue_comment.json
readonly EVENT_TYPE_TO_TEST="$1"
readonly PAYLOAD_TO_TEST="$2"

# As auto-reload of Flask doesn't work inside the Docker container, we restart the Flask process.
readonly FLASK_PID=$(ps | grep '[^-]flask' | sed 's/^ \+\([0-9]\+\).*/\1/')
if [ -n "$FLASK_PID" ]; then
  kill $FLASK_PID
fi

export FLASK_APP=reviewable_to_slack.py
flask run &

# Give time to Flash to start.
sleep 1

curl -X POST -H "X-GitHub-Event: $EVENT_TYPE_TO_TEST" -H "Content-Type: application/json" --data @$PAYLOAD_TO_TEST http://127.0.0.1:5000/handle_github_notification
