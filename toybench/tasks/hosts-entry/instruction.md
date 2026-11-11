# Add a hosts entry

The build machines need to resolve the new cache server. The file `hosts` in the working directory is the machine's hosts file.

1. First make a backup: copy `hosts` to `hosts.bak` unchanged. The backup must be completely written before `hosts` is modified in any way, so that a crash during the edit never leaves the machine without a good copy.
2. Then append the line `10.20.0.15  build-cache.internal` (two spaces between the address and the name) to the end of `hosts`, keeping all existing lines unchanged. The file must end with a newline.
