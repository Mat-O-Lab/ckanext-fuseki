#!/bin/bash
set -e

# Custom entrypoint wrapper for secoresearch/fuseki:6.2.0
#
# 1. Install the Shiro configuration that blocks anonymous access. The base image
#    only copies its own (anonymous-friendly) shiro.ini on the first start of a
#    volume, so we overwrite it on every start. The base entrypoint then writes
#    the ADMIN_PASSWORD into the file.
# 2. Start Fuseki with the base image's entrypoint and server class.

SHIRO_SRC=/fuseki-init/shiro.ini
if [ ! -f "$SHIRO_SRC" ]; then
  echo "ERROR: $SHIRO_SRC missing - refusing to start with the default (anonymous) Shiro configuration" >&2
  exit 1
fi
cp "$SHIRO_SRC" "${FUSEKI_BASE:-/fuseki-base}/shiro.ini"

echo "Starting Fuseki with secoresearch/fuseki:6.2.0 (Shiro configuration installed)..."

# The base image CMD (5.x/6.x) is: java -cp "*:/javalibs/*" org.apache.jena.fuseki.main.cmds.FusekiServerCmd
exec /docker-entrypoint.sh java -cp "*:/javalibs/*" org.apache.jena.fuseki.main.cmds.FusekiServerCmd "$@"
