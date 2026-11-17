FROM secoresearch/fuseki:6.2.0

# Entrypoint wrapper and the Shiro configuration that blocks anonymous access.
# The wrapper copies /fuseki-init/shiro.ini to /fuseki-base/shiro.ini on every
# start (the base image only does that on the first start of a volume).
USER root
COPY docker-entrypoint.sh /custom-entrypoint.sh
COPY shiro.ini /fuseki-init/shiro.ini
RUN chmod +x /custom-entrypoint.sh && chmod 644 /fuseki-init/shiro.ini

# Switch back to the fuseki user (UID 1000)
USER 1000

# Use our custom entrypoint which will call the original Fuseki entrypoint
ENTRYPOINT ["/custom-entrypoint.sh"]

# Keep the original CMD from the base image - it runs the java command for Fuseki
# No CMD override needed - inherit from base image
