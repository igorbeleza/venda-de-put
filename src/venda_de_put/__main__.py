import argparse
import sys

from venda_de_put.paths import load_dotenv


def main(argv=None):
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["scrape", "serve", "smoke"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--data-dir", default=None)
    p.add_argument("--force-fundamentus", choices=["true", "false"], default=None)
    args = p.parse_args(argv)
    if args.cmd == "scrape":
        from venda_de_put.scrape import cli_scrape
        force_fundamentus = None if args.force_fundamentus is None else (args.force_fundamentus == "true")
        return cli_scrape(data_dir=args.data_dir, force_fundamentus=force_fundamentus)
    if args.cmd == "smoke":
        from venda_de_put.smoke import cli_smoke
        return cli_smoke()
    from venda_de_put.web.app import cli_serve
    return cli_serve(host=args.host, port=args.port, data_dir=args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
