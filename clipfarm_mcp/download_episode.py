"""Download an authorized, accessible episode into the reusable local library.

The tool uses yt-dlp's ordinary extractors. It does not circumvent DRM,
authentication, paywalls or a site's bot restrictions.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def filename_stem(season: int, episode: int, title: str) -> str:
    if not (1 <= season <= 99 and 1 <= episode <= 999):
        raise ValueError("season must be 1–99 and episode must be 1–999")
    safe_title = re.sub(r"[^A-Za-z0-9]+", ".", title).strip(".") or "Episode"
    return f"Family.Guy.S{season:02d}E{episode:02d}.{safe_title}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="authorized video source URL")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--title", default="Episode")
    parser.add_argument("--library", type=Path, default=Path(r"D:\fmailyguy"))
    parser.add_argument("--rights-confirmed", action="store_true",
                        help="confirm authorization to download and edit this episode")
    parser.add_argument("--check-only", action="store_true",
                        help="inspect available formats; do not download")
    args = parser.parse_args(argv)
    if not args.rights_confirmed:
        parser.error("confirm authorization with --rights-confirmed")
    try:
        stem = filename_stem(args.season, args.episode, args.title)
    except ValueError as exc:
        parser.error(str(exc))

    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    folder = args.library / f"Season {args.season:02d}"
    if not args.check_only:
        folder.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bv[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "outtmpl": str(folder / (stem + ".%(ext)s")),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "nooverwrites": True,
        "js_runtimes": {"node": {}},
        "skip_download": args.check_only,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(args.url, download=not args.check_only)
    except DownloadError as exc:
        print(f"Could not access the source: {exc}", file=sys.stderr)
        print("Use an accessible, authorized download; protected streams are not supported.",
              file=sys.stderr)
        return 1
    print(f"{'Checked' if args.check_only else 'Saved'}: {info.get('title', stem)}")
    if not args.check_only:
        print(f"Library: {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
