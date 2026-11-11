def all_tags(posts):
    seen = {}
    for post in posts:
        for tag in post["tags"]:
            norm = tag.strip().lower()
            if norm:
                seen.setdefault(norm, None)
    return list(seen)
