#!/bin/sh
set -eu

mkdir -p /var/data/raw /var/data/vectorstore /var/data/huggingface
chown medibot:medibot /var/data /var/data/raw /var/data/vectorstore /var/data/huggingface
exec gosu medibot "$@"
