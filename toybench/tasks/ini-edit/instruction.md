# Edit the service configuration

Edit `app.ini` in place:

1. In the `[database]` section, change the line `pool_size = 5` to `pool_size = 20`.
2. In the `[cache]` section, insert a new line `timeout = 15` directly after the line `url = redis://cache.internal:6379/0`.

Every other line, including comments, blank lines, and their order, must stay exactly as it is. The file must still end with a newline.
