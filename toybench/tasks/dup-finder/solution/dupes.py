def duplicate_groups(files):
    by_content = {}
    for path, content in files.items():
        by_content.setdefault(content, []).append(path)
    groups = [sorted(paths) for paths in by_content.values() if len(paths) > 1]
    return sorted(groups)
