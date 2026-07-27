#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

API_URL = "https://api-prod.ilpost.it/podcast/v3/bff/podcast/227474"
API_KEY = os.getenv("ILPOST_API_KEY", "testapikey")
USER_AGENT = "IlPostApp"
OUTPUT_FILE = Path(os.getenv("OUTPUT_FILE", "feed.xml"))
MAX_EPISODES = int(os.getenv("MAX_EPISODES", "100"))

NS_ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
NS_ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", NS_ITUNES)
ET.register_namespace("atom", NS_ATOM)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def duration_hms(milliseconds: int | None, minutes: int | None) -> str:
    seconds = int((milliseconds or 0) / 1000)
    if seconds <= 0 and minutes:
        seconds = int(minutes) * 60
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def fetch_json() -> dict:
    headers = {
        "apikey": API_KEY,
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    response = requests.get(API_URL, headers=headers, timeout=30)
    if response.status_code in (401, 403):
        raise RuntimeError(f"Errore di autenticazione API: HTTP {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    if payload.get("head", {}).get("status") != 200:
        raise RuntimeError("L'API ha risposto, ma non ha restituito uno stato applicativo 200.")
    return payload


def audio_length(url: str) -> int:
    try:
        response = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            timeout=20,
        )
        if response.ok:
            return int(response.headers.get("Content-Length", "0") or "0")
    except requests.RequestException:
        pass
    return 0


def existing_items(path: Path) -> dict[str, ET.Element]:
    if not path.exists():
        return {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    channel = root.find("channel")
    if channel is None:
        return {}
    found: dict[str, ET.Element] = {}
    for item in channel.findall("item"):
        guid = item.findtext("guid")
        if guid:
            found[guid] = item
    return found


def add_text(parent: ET.Element, tag: str, text: str | None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    element.text = text or ""
    return element


def build_item(ep: dict) -> ET.Element:
    item = ET.Element("item")
    guid = f"ilpost-morning-{ep['id']}"

    title = html.unescape(ep.get("title", "")).strip()
    description = clean_text(ep.get("content_html") or ep.get("summary"))
    page_url = ep.get("url") or ep.get("share_url") or ""
    audio_url = ep.get("episode_raw_url") or ""
    published = parse_date(ep["date"])

    add_text(item, "title", title)
    add_text(item, "link", page_url)
    add_text(item, "guid", guid, isPermaLink="false")
    add_text(item, "pubDate", format_datetime(published))
    add_text(item, "description", description)
    add_text(item, f"{{{NS_ITUNES}}}summary", description)
    add_text(item, f"{{{NS_ITUNES}}}author", ep.get("author") or "Il Post")
    add_text(item, f"{{{NS_ITUNES}}}duration",
             duration_hms(ep.get("milliseconds"), ep.get("minutes")))
    ET.SubElement(
        item,
        "enclosure",
        {
            "url": audio_url,
            "length": str(audio_length(audio_url)),
            "type": "audio/mpeg",
        },
    )

    image = ep.get("image") or ep.get("parent", {}).get("image")
    if image:
        ET.SubElement(item, f"{{{NS_ITUNES}}}image", {"href": image})

    return item


def write_feed(payload: dict) -> None:
    podcast = payload["data"]["podcast"]["data"]
    episodes = payload["data"]["episodes"]["data"]
    previous = existing_items(OUTPUT_FILE)

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    title = podcast.get("title", "Morning")
    description = podcast.get("description", "Comincia la giornata con la rassegna stampa del Post.")
    page_url = podcast.get("share_url", "https://www.ilpost.it/podcasts/morning/")
    image = podcast.get("image") or podcast.get("image_web")
    author = podcast.get("author") or "Il Post"

    add_text(channel, "title", title)
    add_text(channel, "link", page_url)
    add_text(channel, "description", description)
    add_text(channel, "language", "it-IT")
    add_text(channel, "copyright", "Contenuti © Il Post. Feed personale non ufficiale.")
    add_text(channel, f"{{{NS_ITUNES}}}author", author)
    add_text(channel, f"{{{NS_ITUNES}}}summary", description)
    add_text(channel, f"{{{NS_ITUNES}}}explicit", "false")
    ET.SubElement(channel, f"{{{NS_ITUNES}}}category", {"text": "News"})
    ET.SubElement(
        channel,
        f"{{{NS_ATOM}}}link",
        {
            "href": os.getenv(
    "SELF_URL",
    "https://scumaci74.github.io/mf-7c29-feed/feed.xml",
),
        },
    )

    if image:
        image_node = ET.SubElement(channel, "image")
        add_text(image_node, "url", image)
        add_text(image_node, "title", title)
        add_text(image_node, "link", page_url)
        ET.SubElement(channel, f"{{{NS_ITUNES}}}image", {"href": image})

    current_guids = set()
    all_items: list[tuple[datetime, ET.Element]] = []

    for ep in episodes:
        if ep.get("parent", {}).get("slug") != "morning":
            continue
        item = build_item(ep)
        guid = item.findtext("guid") or ""
        current_guids.add(guid)
        all_items.append((parse_date(ep["date"]), item))

    for guid, item in previous.items():
        if guid in current_guids:
            continue
        pub_date = item.findtext("pubDate")
        try:
            parsed = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            parsed = datetime.min.astimezone()
        all_items.append((parsed, item))

    all_items.sort(key=lambda pair: pair[0], reverse=True)

    for _, item in all_items[:MAX_EPISODES]:
        channel.append(item)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)


def main() -> int:
    try:
        payload = fetch_json()
        write_feed(payload)
        count = len(ET.parse(OUTPUT_FILE).getroot().find("channel").findall("item"))
        print(f"Feed aggiornato: {OUTPUT_FILE} ({count} episodi)")
        return 0
    except requests.Timeout:
        print("Errore: timeout durante la chiamata API.", file=sys.stderr)
    except requests.RequestException as exc:
        print(f"Errore HTTP/API: {exc}", file=sys.stderr)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"Errore nei dati: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
