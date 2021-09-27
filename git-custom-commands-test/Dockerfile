FROM lascap/aruba-test

ENV PYTHONUNBUFFERED=1
# Install git and python 3.
RUN apt-get update -qq && apt-get install -qqy git; \
    apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python; \
    python3 -m ensurepip; \
    pip3 install --no-cache --upgrade pip setuptools

# "Install" git-submit.
ADD bin /usr/bin
COPY git-custom-commands-test /test
RUN cucumber
