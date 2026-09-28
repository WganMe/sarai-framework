The framework's connection settings and API keys do NOT live in this repository.

They were moved out of the tree on 2026-09-25 to avoid accidental inclusion in
any archive, sync or upload. They now live at:

    ~/.config/bcdr-secrets/sarai-framework.env     (mode 600)

Load them before running any framework script:

    set -a; source ~/.config/bcdr-secrets/sarai-framework.env; set +a

The scripts read plain environment variables (os.environ), so sourcing the file
above is all that is required. Nothing in this repository sources .env
automatically.

Original location, for reference: framework/.env (still gitignored).
