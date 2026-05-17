import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import config


MATCH_FIELDNAMES = [
    "playlist_path",
    "playlist_name",
    "playlist_category",
    "playlist_grouping",
    "playlist_color",
    "playlist_artist",
    "playlist_title",
    "playlist_album",
    "playlist_year",
    "playlist_duration",
    "file_path",
    "file_name",
    "artist",
    "title",
    "album",
    "local_year",
    "match_score",
    "match_confidence",
    "match_status",
    "match_reason",
    "target_grouping",
    "target_color",
]

TITLE_JUNK_PATTERNS = (
    r"\bofficial\s+(music\s+)?video\b",
    r"\bofficial\s+audio\b",
    r"\blyric(s)?\s+video\b",
    r"\bvideo\s+oficial\b",
    r"\baudio\s+oficial\b",
    r"\bhd\b",
    r"\bhq\b",
    r"\bwww\b.*$",
)


@dataclass
class LabelTrack:
    """LabelTrack."""
    playlist_path: str
    playlist_name: str
    category: str
    grouping: str
    color: str
    artist: str = ""
    title: str = ""
    album: str = ""
    year: str = ""
    duration: str = ""


def clean_title(value):
    """Clean title."""
    text = Path(value or "").stem
    text = re.sub(r"\[[^\]]*(official|video|lyric|audio|hd|hq|www|mimp3|vmusice|genteflow)[^\]]*\]", " ", text, flags=re.I)
    text = re.sub(r"\([^\)]*(official|video|lyric|audio|hd|hq|www|mimp3|vmusice|genteflow)[^\)]*\)", " ", text, flags=re.I)
    for pattern in TITLE_JUNK_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)
    return config.normalize_text(text)


def clean_artist(value):
    """Clean artist."""
    text = value or ""
    text = re.sub(r"\b(feat|ft|featuring|con|with)\b.*$", " ", text, flags=re.I)
    return config.normalize_text(text)


def primary_artist(value):
    """Primary artist."""
    text = re.split(r"\s*(?:,|&|/|\+|\bx\b|\band\b|\by\b)\s*", value or "", maxsplit=1, flags=re.I)[0]
    return clean_artist(text)


def split_artist_title(value):
    """Split artist title."""
    text = Path(value or "").stem
    parts = re.split(r"\s+-\s+", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", text.strip()


def extract_year(*values):
    """Extract year."""
    for value in values:
        match = re.search(r"\b(19[4-9]\d|20[0-3]\d)\b", value or "")
        if match:
            return match.group(1)
    return ""


def ratio(left, right):
    """Ratio."""
    left = left or ""
    right = right or ""
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if len(left) > 4 and len(right) > 4 and (left in right or right in left):
        return 0.94
    return SequenceMatcher(None, left, right).ratio()


def category_from_playlist_name(playlist_name, explicit_category=""):
    """Category from playlist name."""
    if explicit_category:
        return config.normalize_value_to_category(explicit_category)
    patterns = config.CATEGORY_CONFIG.get("playlist_label_patterns", {})
    normalized_name = config.normalize_text(playlist_name)
    for pattern, category in patterns.items():
        if config.pattern_matches(normalized_name, pattern):
            return config.normalize_value_to_category(category)
    return config.normalize_value_to_category(playlist_name)


def label_track_from_values(playlist_path, playlist_name, category, artist="", title="", album="", year="", duration=""):
    """Label track from values."""
    category = category_from_playlist_name(playlist_name, category)
    grouping = config.category_to_grouping(category)
    color = config.category_to_color(category)
    return LabelTrack(
        playlist_path=str(playlist_path),
        playlist_name=playlist_name,
        category=category,
        grouping=grouping,
        color=color,
        artist=(artist or "").strip(),
        title=(title or "").strip(),
        album=(album or "").strip(),
        year=(year or "").strip(),
        duration=(duration or "").strip(),
    )


def _row_value(row, *names):
    """Row value."""
    lowered = {key.lower().strip(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _attr_value(element, *names):
    """Attr value."""
    attrs = {key.lower().strip(): value for key, value in element.attrib.items()}
    for name in names:
        value = attrs.get(name.lower())
        if value:
            return value
    return ""


def _child_attr_value(element, child_name, *names):
    """Child attr value."""
    for child in element:
        if child.tag.lower().endswith(child_name.lower()):
            value = _attr_value(child, *names)
            if value:
                return value
    return ""


def read_csv_playlist(path, explicit_category=""):
    """Read csv playlist."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    tracks = []
    playlist_name = Path(path).stem
    for row in rows:
        row_playlist = _row_value(row, "playlist", "playlist_name", "list", "folder") or playlist_name
        title = _row_value(row, "title", "track", "track_name", "name", "song")
        artist = _row_value(row, "artist", "artists", "creator", "performer")
        album = _row_value(row, "album", "release")
        year = _row_value(row, "year", "date", "release_year")
        duration = _row_value(row, "duration", "songlength", "length")
        if not title:
            file_value = _row_value(row, "path", "file_path", "filename", "file_name", "url", "uri")
            artist, title = split_artist_title(file_value)
        if title or artist:
            tracks.append(label_track_from_values(path, row_playlist, explicit_category, artist, title, album, year, duration))
    return tracks


def read_xml_playlist(path, explicit_category=""):
    """Read xml playlist."""
    tree = ET.parse(path)
    playlist_name = Path(path).stem
    tracks = []
    for element in tree.iter():
        is_songish = element.tag.lower().endswith("song") or _attr_value(element, "title", "artist", "author", "path", "filepath")
        if is_songish:
            title = _attr_value(element, "title") or _child_attr_value(element, "tags", "title")
            artist = _attr_value(element, "artist", "author") or _child_attr_value(element, "tags", "artist", "author")
            album = _attr_value(element, "album") or _child_attr_value(element, "tags", "album")
            duration = _attr_value(element, "songlength", "duration")
            file_path = _attr_value(element, "path", "filepath", "file")
            year = _attr_value(element, "year") or _child_attr_value(element, "tags", "year") or extract_year(album, title, file_path)
            if not title:
                fallback_artist, title = split_artist_title(file_path)
                artist = artist or fallback_artist
            if title or artist:
                tracks.append(label_track_from_values(path, playlist_name, explicit_category, artist, title, album, year, duration))
    return tracks


def read_m3u_playlist(path, explicit_category=""):
    """Read m3u playlist."""
    playlist_name = Path(path).stem
    tracks = []
    pending_duration = ""
    pending_artist = ""
    pending_title = ""
    for raw_line in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            payload = line.split(":", 1)[1]
            duration_part, _, label = payload.partition(",")
            pending_duration = duration_part.strip()
            pending_artist, pending_title = split_artist_title(label)
            continue
        if line.startswith("#"):
            continue
        artist = pending_artist
        title = pending_title
        if not title:
            artist, title = split_artist_title(line)
        year = extract_year(line, title)
        if title or artist:
            tracks.append(label_track_from_values(path, playlist_name, explicit_category, artist, title, "", year, pending_duration))
        pending_duration = ""
        pending_artist = ""
        pending_title = ""
    return tracks


def read_label_playlist(path, explicit_category=""):
    """Read label playlist."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return read_csv_playlist(path, explicit_category)
    if suffix in {".xml", ".vdjfolder"}:
        return read_xml_playlist(path, explicit_category)
    if suffix in {".m3u", ".m3u8"}:
        return read_m3u_playlist(path, explicit_category)
    raise ValueError(f"Unsupported label playlist format: {path}")


def local_identity(row):
    """Local identity."""
    artist = row.get("artist") or ""
    title = row.get("title") or ""
    album = row.get("album") or ""
    file_name = row.get("file_name") or row.get("file_path") or ""
    if not artist or not title:
        fallback_artist, fallback_title = split_artist_title(file_name)
        artist = artist or fallback_artist
        title = title or fallback_title
    year = extract_year(album, title, file_name, row.get("file_path", ""))
    return {
        "artist": artist,
        "title": title,
        "album": album,
        "year": year,
        "clean_artist": clean_artist(artist),
        "primary_artist": primary_artist(artist),
        "clean_title": clean_title(title),
        "clean_album": config.normalize_text(album),
    }


def score_match(label, row):
    """Score match."""
    local = local_identity(row)
    label_artist = clean_artist(label.artist)
    label_primary_artist = primary_artist(label.artist)
    label_title = clean_title(label.title)
    label_album = config.normalize_text(label.album)

    artist_score = max(ratio(label_artist, local["clean_artist"]), ratio(label_primary_artist, local["primary_artist"]))
    title_score = ratio(label_title, local["clean_title"])
    album_score = ratio(label_album, local["clean_album"]) if label_album and local["clean_album"] else 0.0
    year_score = 0.0
    year_penalty = False
    if label.year and local["year"]:
        delta = abs(int(label.year) - int(local["year"]))
        year_score = 1.0 if delta == 0 else (0.7 if delta == 1 else 0.0)
        year_penalty = delta > 1

    if artist_score < 0.84 or title_score < 0.86:
        return 0.0, f"artist/title below strict threshold (artist={artist_score:.2f}, title={title_score:.2f})"

    score = (title_score * 0.55) + (artist_score * 0.35)
    if label_album and local["clean_album"]:
        score += album_score * 0.05
    if label.year and local["year"]:
        score += year_score * 0.05
    else:
        score += 0.025
    if year_penalty:
        score -= 0.12
    return min(1.0, score), f"artist={artist_score:.2f}, title={title_score:.2f}, album={album_score:.2f}, year={label.year or '?'}~{local['year'] or '?'}"


def best_match(label, local_rows):
    """Best match."""
    scored = []
    for row in local_rows:
        score, reason = score_match(label, row)
        if score > 0:
            scored.append((score, reason, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:2]


def match_label_tracks(label_tracks, local_rows, min_score=0.94):
    """Match label tracks."""
    output_rows = []
    for label in label_tracks:
        matches = best_match(label, local_rows)
        if not matches:
            output_rows.append(match_output_row(label, None, 0.0, "review", "No strict artist/title match found"))
            continue
        best_score, reason, row = matches[0]
        ambiguous = len(matches) > 1 and (best_score - matches[1][0]) < 0.03
        if best_score >= min_score and not ambiguous:
            confidence = "high"
            target_grouping = label.grouping
            target_color = label.color
        else:
            confidence = "review"
            target_grouping = ""
            target_color = ""
            if ambiguous:
                reason = f"{reason}; ambiguous second match score={matches[1][0]:.2f}"
            else:
                reason = f"{reason}; below min score {min_score:.2f}"
        output_rows.append(match_output_row(label, row, best_score, confidence, reason, target_grouping, target_color))
    return output_rows


def match_output_row(label, row, score, confidence, reason, target_grouping="", target_color=""):
    """Match output row."""
    row = row or {}
    local = local_identity(row) if row else {"year": ""}
    if target_grouping and confidence == "high":
        match_status = "matched"
    elif row:
        match_status = "review"
    else:
        match_status = "unmatched"
    return {
        "playlist_path": label.playlist_path,
        "playlist_name": label.playlist_name,
        "playlist_category": label.category,
        "playlist_grouping": label.grouping,
        "playlist_color": label.color,
        "playlist_artist": label.artist,
        "playlist_title": label.title,
        "playlist_album": label.album,
        "playlist_year": label.year,
        "playlist_duration": label.duration,
        "file_path": row.get("file_path", ""),
        "file_name": row.get("file_name", ""),
        "artist": row.get("artist", ""),
        "title": row.get("title", ""),
        "album": row.get("album", ""),
        "local_year": local.get("year", ""),
        "match_score": f"{score:.3f}",
        "match_confidence": confidence,
        "match_status": match_status,
        "match_reason": reason,
        "target_grouping": target_grouping,
        "target_color": target_color,
    }


def load_label_playlists(paths, explicit_category=""):
    """Load label playlists."""
    tracks = []
    for path in paths:
        tracks.extend(read_label_playlist(path, explicit_category))
    return tracks
