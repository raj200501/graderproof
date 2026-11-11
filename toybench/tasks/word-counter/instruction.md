# Word-count helper script

The editors want a small command to count words in their drafts.

Create an executable bash script at `bin/wordcount` (create the `bin/` directory). When run as `bin/wordcount FILE`, it must print the number of words in FILE as a plain decimal integer on a single line, and exit with status 0. A word is a maximal run of non-whitespace characters, which is what `wc -w` counts; an empty file has 0 words.

The script must start with `#!/usr/bin/env bash` or `#!/bin/bash` and may use only bash and coreutils.
