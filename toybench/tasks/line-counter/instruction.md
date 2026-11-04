# Log line counter

The operations team wants a quick way to see how much a service has logged.

Create an executable bash script at `bin/countlines` (create the `bin/` directory). When run as `bin/countlines DIR`, it must print the total number of lines in all regular files directly inside DIR whose names end in `.log` (files in subdirectories do not count), as a plain decimal integer on one line, and exit with status 0.

- Count lines the way `wc -l` does, that is, the number of newline characters.
- If DIR contains no such files, print `0`.
- The script must start with `#!/usr/bin/env bash` or `#!/bin/bash` and may use only bash and coreutils.
