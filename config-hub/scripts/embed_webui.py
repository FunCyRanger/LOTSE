#!/usr/bin/env python3
"""Convert webui/ files to gzip-compressed C byte array header for ESP-IDF embedding.

Serves files with Content-Encoding: gzip so the browser decompresses
transparently.  This reduces flash usage ~3× compared to raw C strings.
"""
import os, sys, re, glob, gzip

WEBUI_DIR = os.path.join(os.path.dirname(__file__), '..', 'webui')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'main', 'html.h')

def c_byte_array(data):
    """Produce a C-style uint8_t array initializer from a bytes object."""
    parts = []
    for i, b in enumerate(data):
        if i % 16 == 0:
            parts.append('\n    ')
        parts.append(f'0x{b:02x},')
    return ''.join(parts).rstrip(',')

def main():
    files = glob.glob(os.path.join(WEBUI_DIR, '*'))
    if not files:
        print("No files in webui/")
        sys.exit(1)

    lines = ['#pragma once', '', '#include <stddef.h>', '#include <stdint.h>', '']

    for fpath in sorted(files):
        name = os.path.basename(fpath)
        ext = os.path.splitext(name)[1].lower()
        varname = 'HTML_' + re.sub(r'[^a-zA-Z0-9]', '_', name).upper()

        content_type = {
            '.html': 'text/html',
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.json': 'application/json',
            '.png': 'image/png',
            '.ico': 'image/x-icon',
            '.svg': 'image/svg+xml',
        }.get(ext, 'text/plain')

        with open(fpath, 'rb') as f:
            raw = f.read()

        compressed = gzip.compress(raw, mtime=0)
        raw_len = len(raw)
        comp_len = len(compressed)
        saved = raw_len - comp_len
        pct = (100 * saved // raw_len) if raw_len > 0 else 0

        lines.append(f'/* {name}: {raw_len} raw → {comp_len} gzip ({pct}% savings) */')
        lines.append(f'static const uint8_t {varname}[] = {{{c_byte_array(compressed)}')
        lines.append(f'}};')
        lines.append(f'static const size_t {varname}_LEN = sizeof({varname});')
        lines.append(f'static const char *{varname}_TYPE = "{content_type}";')
        lines.append(f'static const char *{varname}_PATH = "/{name}";')
        lines.append(f'#define {varname}_GZIPPED 1')
        lines.append('')

    with open(OUTPUT, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Generated {OUTPUT} ({len(lines)} lines, {saved} bytes saved on {name})")

if __name__ == '__main__':
    main()
