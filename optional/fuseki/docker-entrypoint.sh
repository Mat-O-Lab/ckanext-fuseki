#!/bin/bash
set -e

# Custom entrypoint wrapper for secoresearch/fuseki:6.2.0
# Since we only mount /fuseki-base/databases as a volume, all other directories
# and configuration files from the image remain intact

echo "Starting Fuseki with secoresearch/fuseki:6.2.0..."

# Execute the original Fuseki entrypoint with the base image's CMD
# The base image CMD (5.x/6.x) is: java -cp "*:/javalibs/*" org.apache.jena.fuseki.main.cmds.FusekiServerCmd
exec /docker-entrypoint.sh java -cp "*:/javalibs/*" org.apache.jena.fuseki.main.cmds.FusekiServerCmd "$@"
