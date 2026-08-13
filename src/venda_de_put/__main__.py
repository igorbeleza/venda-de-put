import argparse
import sys


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["scrape", "serve", "smoke"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    if args.cmd == "scrape":
        from venda_de_put.scrape import cli_scrape
        return cli_scrape()
    if args.cmd == "smoke":
        from venda_de_put.smoke import cli_smoke
        return cli_smoke()
    from venda_de_put.web.app import cli_serve
    return cli_serve(host=args.host, port=args.port)


if __name__ == "__main__":
    sys.exit(main())
