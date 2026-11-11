# Tune the web server configuration

The web server in front of the booking site needs more concurrent connections and shorter idle keep-alives. The configuration file is `nginx.conf` in the working directory.

1. Before editing anything, save an exact copy of the original file as `nginx.conf.orig` in the same directory.
2. In `nginx.conf`, change `worker_connections 1024;` to `worker_connections 4096;`.
3. In `nginx.conf`, change `keepalive_timeout 65;` to `keepalive_timeout 30;`.

Leave everything else in `nginx.conf` byte-for-byte unchanged, including indentation, comments, and blank lines.
