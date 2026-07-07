from pathlib import Path


CONFIG_PATH = Path("/etc/nginx/conf.d/top.tejarvis.info.conf")
SNIPPET_PATH = Path("/tmp/ecommerce-dispute-tool.nginx.conf")
MARKER = "    location / {"
LOCATION_MARKER = "location ^~ /ecommerce-dispute-tool/"


def main():
    config = CONFIG_PATH.read_text()
    if LOCATION_MARKER in config:
        return
    snippet = SNIPPET_PATH.read_text().rstrip()
    if MARKER not in config:
        raise SystemExit(f"Cannot find insertion marker: {MARKER}")
    CONFIG_PATH.write_text(config.replace(MARKER, f"{snippet}\n\n{MARKER}", 1))


if __name__ == "__main__":
    main()
