#!/usr/bin/env python3
"""Convert webui/ files to C string header for ESP-IDF embedding."""
import os, sys, re, glob

WEBUI_DIR = os.path.join(os.path.dirname(__file__), '..', 'webui')
OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'main', 'html.h')

def escape_c_line(text):
    result = []
    for ch in text:
        if ch == '\\':
            result.append('\\\\')
        elif ch == '"':
            result.append('\\"')
        elif ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)

def main():
    files = glob.glob(os.path.join(WEBUI_DIR, '*'))
    if not files:
        print("No files in webui/")
        sys.exit(1)

    lines = ['#pragma once', '', '#include <stddef.h>', '']

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

        with open(fpath) as f:
            content = f.read()

        # Build C string with concatenated line literals
        src_lines = content.split('\n')
        parts = []
        for i, src_line in enumerate(src_lines):
            escaped = escape_c_line(src_line)
            parts.append(f'"{escaped}\\n"')

        joined = '\n    '.join(parts)
        lines.append(f'static const char {varname}[] =')
        lines.append(f'    {joined};')
        lines.append(f'static const size_t {varname}_LEN = sizeof({varname}) - 1;')
        lines.append(f'static const char *{varname}_TYPE = "{content_type}";')
        lines.append(f'static const char *{varname}_PATH = "/{name}";')
        lines.append('')

    with open(OUTPUT, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Generated {OUTPUT} ({len(lines)} lines)")

if __name__ == '__main__':
    main()
