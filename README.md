# Forge & Hide deployment

## PythonAnywhere deployment

The current PythonAnywhere account is on the free plan, where scheduled tasks are
not enabled. After each push to GitHub, run the deploy command below in a
PythonAnywhere Bash console. It fast-forwards a clean `main` checkout, installs
requirements only when they changed, applies committed database migrations, and
touches the WSGI file to reload the app.

This deploys **committed changes pushed to `main`**. This checkout also exports
the local catalog when you commit: categories, products, galleries, homepage
banners, and only the images those rows use. The Made-to-Order photo is included
too. Orders, order items, customers, and admin accounts are never exported.
PythonAnywhere makes a database backup before importing changed catalog data,
preserves stock for products already on the live site, and keeps removed
products in the database but hides them from the storefront.

### Push all saved project changes from VS Code

1. Save all files and product/banner changes in the local site.
2. In VS Code **Source Control**, choose **Stage All Changes**, review the list,
   enter a commit message, then choose **Commit** and **Sync Changes**. The
   pre-commit hook refreshes the catalog snapshot and adds it to the commit.
   The local database itself, orders, customers, admin accounts, virtualenv,
   `.env`, and unused uploaded images are not pushed.
3. Use a PythonAnywhere Bash console and run:

   ```bash
   source /home/ForgenHide/.virtualenvs/forge-env/bin/activate
   cd /home/ForgenHide/Forge-and-Hide
   bash scripts/deploy_pythonanywhere.sh /var/www/forgenhide_pythonanywhere_com_wsgi.py
   ```

The script stops safely if the branch is not `main`, the checkout has local
changes, the update is not a fast-forward, the virtualenv is not active, or the
WSGI path is invalid. If a deployment is blocked by local changes, inspect them
before resolving anything; do not use `git reset --hard`.

The pre-commit hook is enabled for this checkout. If you clone the project
again on another computer, enable it once with:

```bash
git config core.hooksPath .githooks
```

Model changes need a committed migration under `migrations/versions/`; the
deploy script applies committed migrations with `flask db upgrade`. Paid
PythonAnywhere accounts can run the same command as a scheduled task if desired.