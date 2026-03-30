#!/bin/bash
export GIT_SSH_COMMAND="ssh -i /tmp/ftp-web-keys/deploy-key -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o ProxyCommand='nc -X 5 -x 10.43.0.1:1080 %h %p'"
cd /home/node/.openclaw/workspace/ftp-web-preview
git push origin master --force
