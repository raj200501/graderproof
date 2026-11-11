# Archive old application logs

The directory `logs/` holds one log file per day, named `app-YYYY-MM-DD.log`. The disk is filling up and older logs are being moved to an archive directory that is backed up separately.

Move every log file in `logs/` dated before 2026-10-01 into the directory `logs/archive/` (create it). Keep each moved file's name and contents unchanged. Files dated 2026-10-01 or later stay in `logs/` untouched. Do not delete, rename, or create any other file.
