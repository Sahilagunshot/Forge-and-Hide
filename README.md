# Forge & Hide deployment

## PythonAnywhere deployment

The current PythonAnywhere account is on the free plan, where scheduled tasks are
not enabled. After each push to GitHub, run the deploy command below in a
PythonAnywhere Bash console. It fast-forwards a clean `main` checkout, installs
requirements only when they changed, applies committed database migrations, and
touches the WSGI file to reload the app.

This deploys **committed changes pushed to `main`**. Unsaved files, other local
folders, and untracked/ignored files are not included. New product or banner data
entered in a local database, and new files under `static/uploads/`, are not
synced by Git. Add or update that content on the live site separately; never
replace the live database with a local copy because it contains production data.

### Push all saved project changes from VS Code

1. Save all files that belong to this project.
2. In VS Code **Source Control**, choose **Stage All Changes**, review the list,
   enter a commit message, then choose **Commit** and **Sync Changes**. Git
   ignores the local database, virtualenv, `.env`, and new `static/uploads/`
   files; review changes before committing.
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

Model changes need a committed migration under `migrations/versions/`; the
deploy script applies committed migrations with `flask db upgrade`. Paid
PythonAnywhere accounts can run the same command as a scheduled task if desired.