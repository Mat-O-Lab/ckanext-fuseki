FROM secoresearch/fuseki:6.2.0

# Copy our custom entrypoint that handles volume mount initialization
# Need to switch to root temporarily to set permissions
USER root
COPY docker-entrypoint.sh /custom-entrypoint.sh
RUN chmod +x /custom-entrypoint.sh

# Switch back to the fuseki user (UID 1000)
USER 1000

# Use our custom entrypoint which will call the original Fuseki entrypoint
ENTRYPOINT ["/custom-entrypoint.sh"]

# Keep the original CMD from the base image - it runs the java command for Fuseki
# No CMD override needed - inherit from base image
