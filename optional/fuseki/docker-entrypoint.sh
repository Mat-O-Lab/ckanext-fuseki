#!/bin/bash
set -e

# Custom entrypoint wrapper for secoresearch/fuseki:4.9.0
# Since we only mount /fuseki-base/databases as a volume, all other directories
# and configuration files from the image remain intact

echo "Starting Fuseki with secoresearch/fuseki:4.9.0..."

# Execute the original Fuseki entrypoint with the base image's CMD
# The base image CMD is: java -cp "*:/javalibs/*" org.apache.jena.fuseki.cmd.FusekiCmd
exec /docker-entrypoint.sh java -cp "*:/javalibs/*" org.apache.jena.fuseki.cmd.FusekiCmd "$@"
