import os
import sys
from argparse import Namespace

from config import load_all_apps, AppConfig
from github import get_repo_prs, PR
import questionary
import argparse

def choose_app() -> AppConfig:
    print("\n> Loading apps\n")
    apps = load_all_apps()
    if len(apps) == 0:
        print("\n> No apps loaded\n")
        exit(0)
    choices = [
        questionary.Choice(
            title=app.label,
            value=app
        ) for app in apps
    ]
    return questionary.select(
        "Choose which app to test",
        choices=choices,
    ).ask()

def choose_pr(app: AppConfig) -> PR:
    print(f"\n> Loading {app.label} PRs \n")
    prs = get_repo_prs(app.repo)
    choices = [
        questionary.Choice(
            title=f"(#{pr.number}) {pr.title}",
            description=f"{pr.author} - {pr.created_at.strftime('%Y-%m-%d %H:%M')}",
            value=pr
        ) for pr in prs
    ]
    return questionary.select(
        "Choose which PR to test",
        choices=choices,
    ).ask()

def list_apps():
    config_files = os.listdir("repos")
    apps = []
    for filename in config_files:
        apps.append(filename.replace(".json", ""))
    return apps

def main(args: Namespace):
    print()
    if args.command == "list":
        apps = list_apps()
        print("===== Apps =====")
        for app in apps:
            print(app)
        print()
    elif args.command == "run":
        app_arg = args.app
        if app_arg:
            if app_arg not in list_apps():
                print(f"> Unknown app '{app_arg}'\n")
                return
            chosen_app = AppConfig.from_config_file(f"repos/{app_arg}.json")
        else:
            chosen_app = choose_app()
        chosen_pr = choose_pr(chosen_app)
        chosen_app.register_options()
        chosen_app.checkout_branch(chosen_pr.branch)
        if chosen_app.run_test():
            print("\n> Test successful")
        else:
            print("\n> Test failed")
    else:
        print(f"> Unknown command '{args.command}'\n")

def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(
        description="PR testing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.required = True

    # -- list --
    subparsers.add_parser(
        "list",
        help="List configured apps",
        description="List all apps defined in the config file.",
    )

    # -- run --
    run_parser = subparsers.add_parser(
        "run",
        help="Test PRs for an app",
        description="Fetch open PRs for an app's repo and run its test commands.",
    )
    run_parser.add_argument(
        "app",
        nargs="?",  # optional — if omitted you can prompt interactively
        help="App name as defined in the config file",
    )
    run_parser.add_argument(
        "--state",
        default="open",
        choices=["open", "closed", "all"],
        help="PR state to filter by (default: open)",
    )

    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    try:
        main(args)
    except KeyboardInterrupt:
        sys.exit(1)