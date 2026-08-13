import argparse
import sys


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["scrape", "serve", "smoke"])
    args = p.parse_args(argv)
    if args.cmd == "scrape":
        from venda_de_put.scrape import cli_scrape
        return cli_scrape()
    if args.cmd == "smoke":
        from venda_de_put.smoke import cli_smoke
        return cli_smoke()
    from venda_de_put.web.app import cli_serve
    return cli_serve()


if __name__ == "__main__":
    sys.exit(main())
