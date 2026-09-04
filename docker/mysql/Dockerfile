FROM mysql:8.0

COPY docker/mysql/entrypoint-render.sh /usr/local/bin/entrypoint-render.sh
RUN chmod +x /usr/local/bin/entrypoint-render.sh

EXPOSE 3306

# Render mounts the persistent disk at /var/lib/mysql. The wrapper preserves
# the existing data and synchronizes the application password before handing
# control to the official MySQL entrypoint.
ENTRYPOINT ["/usr/local/bin/entrypoint-render.sh"]
CMD ["mysqld"]
