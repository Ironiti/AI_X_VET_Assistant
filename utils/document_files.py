"""Resolve displayed document titles to exact local filenames."""
from pathlib import Path


def blank_file_name(title, directory):
    name = str(title).strip()
    if not name or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Expected a document title, not a path')
    folder = Path(directory)
    suffixes = ('.pdf', '.xlsx', '.xls', '.docx')
    suffix = Path(name).suffix.lower()
    candidates = [name] if suffix in suffixes else [name + ext for ext in suffixes]
    for candidate in candidates:
        if (folder / candidate).is_file():
            return candidate
    # Display formatting replaces underscores with spaces. Compare whole titles
    # only, so a rabies document cannot match an unrelated form by a substring.
    def normalized(value):
        return ' '.join(value.replace('_', ' ').split()).casefold()
    stem = Path(name).stem if suffix in suffixes else name
    matches = [p.name for p in folder.iterdir() if p.is_file()
               and p.suffix.lower() in suffixes
               and (suffix not in suffixes or p.suffix.lower() == suffix)
               and normalized(p.stem) == normalized(stem)] if folder.is_dir() else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f'Ambiguous document title: {name}')
    # Preserve existing PDF cache keys when the file is stored only in the bot.
    return name if suffix in suffixes else name + '.pdf'
